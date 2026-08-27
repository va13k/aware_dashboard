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
    """One ESM in the shape the client's own queue parses."""
    esm: dict = {
        "esm_type": 5 if payload.answers else 1,
        "esm_title": payload.title,
        "esm_instructions": payload.instructions,
        "esm_expiration_threshold": payload.expires,
        "esm_trigger": "dashboard",
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

    async def rows(sql: str) -> list[dict]:
        try:
            result = await db.execute(text(sql), args)
            return [dict(row._mapping) for row in result]
        except SQLAlchemyError:
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
    answered_scope = "WHERE esm_status = 2" + (" AND device_id = :d" if device_id else "")
    answered = await rows(
        "SELECT device_id, esm_title, esm_user_answer, double_esm_user_answer_timestamp AS answered_at "
        f"FROM esms {answered_scope} ORDER BY double_esm_user_answer_timestamp DESC LIMIT :n"
    )
    return {"sent": sent, "delivered": delivered, "answered": answered}
