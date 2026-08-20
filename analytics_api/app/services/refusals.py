"""Writes the micro-server turned away, reported so an attempt is not invisible.

A refused write stores nothing. That is the point of refusing it, and it is also
why the refusal needs a record of its own: everything else the dashboard shows
about a device is read from the rows that device wrote, so a device that never got
a row in is a device the dashboard has no way to notice. The device list learns
about an unrecognised phone from its data; a refused phone leaves none.

Aggregated at the source, one row per (device, reason), so the read is the whole
table and the answer is one small query. A phone retrying every minute for a week
is one line with a rising count and a moving `last_seen` rather than ten thousand
rows to page through.

Reported, not acted on. Nothing here blocks or deletes anything: a refusal already
happened, and what it means is a question about who that device is — which is the
same judgement the enrolment badge asks for, and the researcher's to make.
"""

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

#: Why a write was turned away, and how to say so on screen.
REASONS = {
    "no_enrolment": "no enrolment window the study log put there",
    "no_device_id": "named no device at all",
}

#: What a request that named no device is recorded under.
NO_DEVICE = ""


async def by_device(db: AsyncSession, model) -> list[dict]:
    """Every refusal the table holds, most recently seen first.

    An absent table reads as no refusals rather than an error: the record is
    written by the ingest path, and a deployment whose micro-server has never
    turned a write away has nothing to report.
    """
    try:
        result = await db.execute(select(model).order_by(model.last_seen.desc()))
        rows = result.scalars().all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await db.rollback()
        return []

    return [
        {
            "device_id": str(row.device_id),
            "reason": row.reason,
            "explanation": REASONS.get(row.reason, row.reason),
            "attempts": int(row.attempts or 0),
            "rows_refused": int(row.rows_refused or 0),
            "last_table": row.last_table or "",
            "first_seen": int(row.first_seen or 0),
            "last_seen": int(row.last_seen or 0),
        }
        for row in rows
    ]


async def summary(db: AsyncSession, model) -> dict:
    """One platform's refusals: the totals, and each device behind them.

    `devices` counts the phones that were turned away, excluding the row that
    stands for requests naming no device, since that one is not a device.
    """
    reported = await by_device(db, model)
    return {
        "attempts": sum(entry["attempts"] for entry in reported),
        "rows_refused": sum(entry["rows_refused"] for entry in reported),
        "devices": sum(1 for entry in reported if entry["device_id"] != NO_DEVICE),
        "refusals": reported,
    }
