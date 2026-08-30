"""Reaching a participant, and the record of having done it.

Three states, kept apart because collapsing them misleads. *Sent* is ours and is
written here. *Delivered* is the phone's own row in `mqtt_messages`, uploaded with
the rest of its data --- which makes it evidence rather than an assumption, and means
it lags a sync: a prompt to a quiet phone reads as undelivered until that phone next
uploads, and that is a normal state rather than a failure. *Answered* is the `esms`
row the participant's tap produced.

Sending is an intervention rather than an observation, so two things happen before a
researcher is told it worked: the rate limit is asked, and the send is recorded. A
message whose content the researcher asked not to keep still leaves a row --- the
limit counts these, and a channel to participants that leaves no trace is not one a
study should have. What is optional is the words, not the fact.
"""

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_android_db
from app.services import broker
from shared_config import messaging

router = APIRouter(prefix="/messages", tags=["messages"])

#: The question's own words live inside the ESM payload rather than in a column of
#: their own, which is the client's shape and not ours to change. Read out here so
#: every reader asks the same way --- one that named `esm_title` as a column was
#: answered with an error, and the caller turned that into an empty list of answers.
ESM_TITLE = "JSON_UNQUOTE(JSON_EXTRACT(esm_json, '$.esm_title'))"
ESM_INSTRUCTIONS = "JSON_UNQUOTE(JSON_EXTRACT(esm_json, '$.esm_instructions'))"
ESM_TRIGGER = "JSON_UNQUOTE(JSON_EXTRACT(esm_json, '$.esm_trigger'))"

#: The status the client writes once a participant has answered. The other states a
#: prompt passes through are its own; this is the one that carries an answer.
ANSWERED = 2


MAX_HISTORY = 200


#: Addresses every device the study log recorded joining. A study-wide request is
#: the ordinary case for a configuration update --- what the phones are told has
#: changed, and it has changed for all of them.
ALL_DEVICES = "all"


class SendRequest(BaseModel):
    #: One phone, or ``all``. Kept for a caller addressing a single device, which
    #: is most of them.
    device_id: str = ""
    #: Several phones in one request. The clients subscribe only to topics carrying
    #: their own device id, so a message to a group is a publish per phone whichever
    #: way it is asked for --- and the fan-out belongs here rather than in a browser
    #: making one request per recipient. Each phone is rate-limited and recorded on
    #: its own, so the work is per-device regardless; what this saves is a round trip
    #: each and the half-sent state a failed request in the middle would leave.
    device_ids: list[str] = Field(default_factory=list)
    kind: str = Field(default=messaging.QUESTION)
    title: str = ""
    instructions: str = ""
    answers: list[str] = Field(default_factory=list)
    expires: int = 3600
    #: Whether the message's own words enter the study record. The row is written
    #: either way; this decides whether it carries what was said.
    retain: bool = True


def _esm(payload: SendRequest) -> str:
    """One ESM in the shape the client's own queue parses.

    `esm_keep` is what stops this destroying whatever the participant has not
    answered yet. The client clears its whole queue when a prompt arrives without
    it --- every pending question is marked replaced and its notification
    cancelled (com.aware.ESM#queueESM) --- so a question sent from here would take
    the study's own scheduled prompts down with it.

    A question waits until it is answered; a timed one carries the expiry the
    study set. Zero is the client's own word for "no expiry", so an ad-hoc
    question sends zero rather than an hour nobody chose.
    """
    esm: dict = {
        "esm_type": 5 if payload.answers else 1,
        "esm_title": payload.title,
        "esm_instructions": payload.instructions,
        "esm_expiration_threshold": (
            payload.expires if payload.kind == messaging.TIMED_QUESTION else 0
        ),
        "esm_trigger": "dashboard",
        "esm_keep": True,
    }
    if payload.answers:
        esm["esm_quick_answers"] = payload.answers
    else:
        esm["esm_submit"] = "Send"
    return json.dumps([{"esm": esm}])


def _notice(payload: SendRequest) -> str:
    """A participant-facing notification rendered by the Android MQTT service."""
    return json.dumps(
        {"id": uuid.uuid4().hex, "title": payload.title, "message": payload.instructions}
    )


async def _enrolled(db: AsyncSession) -> list[str]:
    """Every device the study log recorded joining."""
    result = await db.execute(
        text("SELECT device_id FROM device_enrolment GROUP BY device_id ORDER BY MAX(joined_at) DESC")
    )
    return [row[0] for row in result if row[0]]


async def _sent_recently(db: AsyncSession, device_id: str, kind: str) -> int:
    since = int(time.time() * 1000) - messaging.LIMIT_WINDOW_SECONDS * 1000
    result = await db.execute(
        text(
            f"SELECT COUNT(*) FROM {messaging.SENT_TABLE} WHERE device_id = :d "
            "AND kind = :k AND sent_at >= :s"
        ),
        {"d": device_id, "k": kind, "s": since},
    )
    return int(result.scalar() or 0)


KINDS = (
    messaging.SYNC_REQUEST,
    messaging.UPDATE_REQUEST,
    messaging.QUESTION,
    messaging.TIMED_QUESTION,
    messaging.NOTICE,
)


@router.post("/send")
async def send(payload: SendRequest, db: AsyncSession = Depends(get_android_db)):
    if payload.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"{payload.kind!r} is not something to send")

    if payload.device_id == ALL_DEVICES:
        targets = await _enrolled(db)
        if not targets:
            raise HTTPException(status_code=404, detail="No device has joined this study yet.")
    else:
        # Deduplicated and ordered, so a list naming a phone twice sends once and a
        # result can be read against the request that produced it.
        named = list(dict.fromkeys([*payload.device_ids, payload.device_id]))
        targets = [device for device in named if device]
    if not targets:
        raise HTTPException(status_code=400, detail="Name at least one device to send to.")

    if payload.kind in (messaging.SYNC_REQUEST, messaging.UPDATE_REQUEST):
        channel, body = messaging.SYNC, messaging.action_for(payload.kind)
    elif payload.kind == messaging.NOTICE:
        channel, body = messaging.NOTICE_CHANNEL, _notice(payload)
    else:
        channel, body = messaging.ESM, _esm(payload)

    sent, held, failed = [], [], []
    for device in targets:
        # Asked per device even on a study-wide send, so one phone at its limit
        # holds only itself back rather than the whole study.
        refusal = messaging.over_limit(payload.kind, await _sent_recently(db, device, payload.kind))
        if refusal:
            held.append({"device_id": device, "reason": refusal})
            continue
        try:
            broker.publish(messaging.topic(device, channel), body)
        except broker.BrokerUnavailable as error:
            failed.append({"device_id": device, "reason": str(error)})
            continue
        sent.append(device)
        await _record(db, device, channel, payload, body)

    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        # The messages are on their way and cannot be recalled, so this reports what
        # actually happened rather than pretending the send failed.
        return {"sent": sent, "held": held, "failed": failed, "recorded": False}

    if not sent and failed:
        raise HTTPException(status_code=503, detail=failed[0]["reason"])
    if not sent and held:
        raise HTTPException(status_code=429, detail=held[0]["reason"])

    return {
        "sent": sent,
        "held": held,
        "failed": failed,
        "recorded": True,
        "retained": payload.retain,
    }


async def _record(db: AsyncSession, device: str, channel: str, payload: SendRequest, body: str):
    await db.execute(
        text(
            f"INSERT INTO {messaging.SENT_TABLE} "
            "(device_id, channel, kind, title, body, sent_at, sent_by, retained) "
            "VALUES (:d, :c, :k, :t, :b, :s, :u, :r)"
        ),
        {
            "d": device,
            "c": channel,
            "k": payload.kind,
            "t": payload.title if payload.retain else "",
            "b": body if payload.retain else None,
            "s": int(time.time() * 1000),
            "u": "dashboard",
            "r": 1 if payload.retain else 0,
        },
    )


@router.get("/for-device/{device_id}")
async def for_device(
    device_id: str,
    limit: int = Query(100, le=MAX_HISTORY),
    db: AsyncSession = Depends(get_android_db),
):
    """Everything one participant was asked, and what came back from each.

    Two lists rather than one, because only one of the two has an answer to carry.
    A question becomes an ESM the client queues, shows and records the answer to; a
    notice is a notification the client renders and writes nothing about; a sync or
    an update is an instruction it acts on silently. Pairing a notice with an empty
    answer would read as a participant who ignored it, when nothing was ever asked
    of them and nothing would have been recorded if they had replied.

    The prompts are every one the study put in front of this participant --- the
    ones sent from here and the ones its schedules raised --- because what a
    researcher is looking at is a person's answering, not one channel's.
    """
    args = {"d": device_id, "n": limit}

    async def rows(sql: str, extra: dict | None = None) -> list[dict]:
        try:
            result = await db.execute(text(sql), {**args, **(extra or {})})
            return [dict(row._mapping) for row in result]
        except SQLAlchemyError:
            await db.rollback()
            return []

    prompts = await rows(
        f"SELECT timestamp AS shown_at, esm_status AS status, "
        f"{ESM_TITLE} AS title, {ESM_INSTRUCTIONS} AS instructions, "
        f"{ESM_TRIGGER} AS trigger_name, "
        "esm_user_answer AS answer, "
        "double_esm_user_answer_timestamp AS answered_at "
        "FROM esms WHERE device_id = :d ORDER BY timestamp DESC LIMIT :n"
    )
    sent = await rows(
        f"SELECT sent_at, kind, title, body, retained FROM {messaging.SENT_TABLE} "
        "WHERE device_id = :d ORDER BY sent_at DESC LIMIT :n"
    )
    return {"prompts": collapse_prompts(prompts), "sent": sent}


def collapse_prompts(rows: list[dict]) -> list[dict]:
    """One line per prompt, from the several rows a prompt leaves behind.

    The client writes a row for each state a prompt passes through, so a question
    that was answered is in the table twice --- once superseded, once answered, a
    fraction of a second apart and under the same title. Shown as they are, a
    researcher counts every question twice and reads half of them as ignored.
    """
    kept: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("title"), int((row.get("shown_at") or 0) / 1000))
        seen = kept.get(key)
        answered = bool(str(row.get("answer") or "").strip())
        if seen is None or (answered and not seen["answered"]):
            kept[key] = {**row, "answered": answered}
    return sorted(kept.values(), key=lambda r: r.get("shown_at") or 0, reverse=True)


@router.get("/history")
async def history(
    device_id: str | None = Query(None),
    limit: int = Query(50, le=MAX_HISTORY),
    db: AsyncSession = Depends(get_android_db),
):
    """What was asked of each phone, what it recorded receiving, and what came back."""
    scope = "WHERE device_id = :d" if device_id else ""
    args: dict = {"n": limit}
    if device_id:
        args["d"] = device_id

    async def rows(sql: str, extra: dict | None = None) -> list[dict]:
        try:
            result = await db.execute(text(sql), {**args, **(extra or {})})
            return [dict(row._mapping) for row in result]
        except SQLAlchemyError:
            # A study whose schema predates one of these tables still gets the rest,
            # rather than a page that fails whole because one question cannot be
            # asked. What this must not swallow is a query that is simply wrong ---
            # `esm_title` was read as a column for exactly as long as nobody noticed
            # the answers had stopped arriving.
            await db.rollback()
            return []

    sent = await rows(
        f"SELECT _id, device_id, kind, title, sent_at, retained FROM {messaging.SENT_TABLE} "
        f"{scope} ORDER BY sent_at DESC LIMIT :n"
    )
    delivered = await rows(
        f"SELECT device_id, topic, timestamp FROM mqtt_messages {scope} "
        "ORDER BY timestamp DESC LIMIT :n"
    )
    answered_scope = "WHERE esm_status = :answered" + (" AND device_id = :d" if device_id else "")
    answered = await rows(
        f"SELECT device_id, {ESM_TITLE} AS esm_title, esm_user_answer, "
        "double_esm_user_answer_timestamp AS answered_at "
        f"FROM esms {answered_scope} ORDER BY double_esm_user_answer_timestamp DESC LIMIT :n",
        {"answered": ANSWERED},
    )
    return {"sent": sent, "delivered": delivered, "answered": answered}
