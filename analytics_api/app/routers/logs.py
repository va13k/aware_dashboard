"""Client operation logs (`aware_log`).

Exposes the free-form log lines the client emits about its own operation, both
study-wide (all devices, for the Overview) and filtered to one device over a
window (for the device page). Rows are grouped by `log_type`, which the UI uses
as the "stream to track" filter.

Both platforms, under parallel routes. Android stores `log_type` and
`log_message` as columns; an iPhone stores one JSON blob per row whose
`log_message` is itself JSON, so the iOS routes project that blob into the same
two fields: the raw text as the message, and the emitting `class` as the type.
"""

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import JSON, distinct, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_android_db, get_ios_db
from app.models import AndroidAwareLog, IosAwareLog
from app.schemas import AwareLogSchema
from app.services.series import clamp_window

router = APIRouter(prefix="/logs", tags=["logs"])

# A page of log lines. Logs are browsed and searched, not bulk-pulled as JSON —
# a full dump goes through the CSV export below.
MAX_LOG_LIMIT = 500


def _filters(device_id, log_type, from_ts, to_ts, q):
    """The WHERE conditions shared by the list, count and export queries."""
    conds = []
    if device_id:
        conds.append(AndroidAwareLog.device_id == device_id)
    # `log_type=""` is a real value (many rows carry an empty type), so filter
    # whenever the param is present; only its absence (None) means "any type".
    if log_type is not None:
        conds.append(AndroidAwareLog.log_type == log_type)
    if from_ts is not None:
        conds.append(AndroidAwareLog.timestamp >= from_ts)
    if to_ts is not None:
        conds.append(AndroidAwareLog.timestamp <= to_ts)
    if q:
        conds.append(AndroidAwareLog.log_message.ilike(f"%{q}%"))
    return conds


async def _rollback(db: AsyncSession):
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


@router.get("/android/log-types")
async def android_log_types(db: AsyncSession = Depends(get_android_db)):
    """The distinct `log_type` values present, for the filter control."""
    try:
        result = await db.execute(
            select(distinct(AndroidAwareLog.log_type)).order_by(
                AndroidAwareLog.log_type
            )
        )
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return []
    return [value for (value,) in result.all() if value is not None]


@router.get("/android")
async def list_android_logs(
    device_id: str | None = Query(None),
    log_type: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    q: str | None = Query(None, description="Substring match on log_message"),
    limit: int = Query(100, le=MAX_LOG_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_android_db),
):
    """A page of log lines (newest first) plus the total matching the filters."""
    conds = _filters(device_id, log_type, from_ts, to_ts, q)
    try:
        total = (
            await db.execute(
                select(func.count()).select_from(AndroidAwareLog).where(*conds)
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(AndroidAwareLog)
                .where(*conds)
                .order_by(AndroidAwareLog.timestamp.desc(), AndroidAwareLog._id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {"total": 0, "rows": []}

    return {
        "total": int(total),
        "rows": [AwareLogSchema.model_validate(r).model_dump() for r in rows],
    }


@router.get("/android/export")
async def export_android_logs(
    device_id: str | None = Query(None),
    log_type: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    q: str | None = Query(None, description="Substring match on log_message"),
    db: AsyncSession = Depends(get_android_db),
):
    """Every matching log line as CSV. The scan is bounded to a year by default
    (see `clamp_window`); an explicit `from_ts`/`to_ts` narrows it further."""
    from_ts, to_ts = clamp_window(from_ts, to_ts)
    conds = _filters(device_id, log_type, from_ts, to_ts, q)
    try:
        rows = (
            await db.execute(
                select(AndroidAwareLog)
                .where(*conds)
                .order_by(AndroidAwareLog.timestamp.asc(), AndroidAwareLog._id.asc())
            )
        ).scalars().all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        rows = []

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["id", "timestamp", "device_id", "log_type", "log_message"]
    )
    writer.writeheader()
    for row in rows:
        record = AwareLogSchema.model_validate(row).model_dump()
        ts = record["timestamp"]
        record["timestamp"] = datetime.fromtimestamp(
            ts / 1000 if ts >= 1e11 else ts, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        writer.writerow(record)

    scope = device_id or "all"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="android_logs_{scope}.csv"'},
    )


# An iPhone's log row is `{"timestamp", "device_id", "log_message"}` inside the
# `data` column, and `log_message` holds JSON of its own: the class that emitted
# the event and what happened. These read that nesting one level at a time so a
# row whose message is not JSON still yields its text.
_IOS_MESSAGE = IosAwareLog.data.op("->>")("$.log_message")
_IOS_CLASS = func.json_unquote(
    func.json_extract(func.cast(_IOS_MESSAGE, JSON), "$.class")
)


def _ios_filters(device_id, log_type, from_ts, to_ts, q):
    conds = []
    if device_id:
        conds.append(IosAwareLog.device_id == device_id)
    if from_ts is not None:
        conds.append(IosAwareLog.timestamp >= from_ts)
    if to_ts is not None:
        conds.append(IosAwareLog.timestamp <= to_ts)
    if log_type is not None:
        conds.append(_IOS_CLASS == log_type)
    if q:
        conds.append(_IOS_MESSAGE.like(f"%{q}%"))
    return conds


def _ios_row(row) -> dict:
    """One iPhone log line in the shape the page already renders.

    Built through the same schema as the Android rows, so the two endpoints
    answer with identical fields rather than with two hand-written dictionaries
    that agree until one of them changes.
    """
    record, log_type = row
    payload = record.data if isinstance(record.data, dict) else {}
    return AwareLogSchema.model_validate(
        {
            "_id": record._id,
            "timestamp": record.timestamp,
            "device_id": record.device_id,
            "log_type": log_type or "",
            "log_message": payload.get("log_message", ""),
        }
    ).model_dump()


@router.get("/ios/log-types")
async def ios_log_types(db: AsyncSession = Depends(get_ios_db)):
    """The distinct emitting classes, standing in for Android's `log_type`."""
    try:
        result = await db.execute(select(distinct(_IOS_CLASS)).order_by(_IOS_CLASS))
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return []
    return [value for (value,) in result.all() if value is not None]


@router.get("/ios")
async def list_ios_logs(
    device_id: str | None = Query(None),
    log_type: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    q: str | None = Query(None, description="Substring match on the log message"),
    limit: int = Query(100, le=MAX_LOG_LIMIT),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_ios_db),
):
    conds = _ios_filters(device_id, log_type, from_ts, to_ts, q)
    try:
        total = (
            await db.execute(
                select(func.count()).select_from(IosAwareLog).where(*conds)
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(IosAwareLog, _IOS_CLASS)
                .where(*conds)
                .order_by(IosAwareLog.timestamp.desc(), IosAwareLog._id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {"total": 0, "rows": []}

    return {"total": int(total), "rows": [_ios_row(row) for row in rows]}


@router.get("/ios/export")
async def export_ios_logs(
    device_id: str | None = Query(None),
    log_type: str | None = Query(None),
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_ios_db),
):
    conds = _ios_filters(device_id, log_type, from_ts, to_ts, q)
    try:
        rows = (
            await db.execute(
                select(IosAwareLog, _IOS_CLASS)
                .where(*conds)
                .order_by(IosAwareLog.timestamp.desc(), IosAwareLog._id.desc())
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        rows = []

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=["_id", "timestamp", "device_id", "log_type", "log_message"]
    )
    writer.writeheader()
    writer.writerows(_ios_row(row) for row in rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ios-logs-{stamp}.csv"'},
    )
