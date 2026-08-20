"""Devices a researcher has taken out of the analysis.

Withdrawal and exclusion answer different questions, and folding them together
would answer one of them silently. Closing an enrolment window stops new data
arriving. What happens to the data already collected — kept, left out of the
analysis, or removed — is a question consent forms answer differently, so it is a
separate and deliberate action with its own confirmation.

The default is the conservative one: withdrawal keeps what was collected, and a
device is excluded only because somebody said so.

An exclusion is not a deletion and not a hiding. The rows stay in the database and
the device stays on screen, marked: a participant the dashboard had quietly dropped
would be indistinguishable from one who never took part, which is the same
discrepancy the orphan-row reporting exists to prevent. What an exclusion changes
is the exports, because that is where the analysis dataset actually leaves. A
researcher who then wants the rows gone asks a database administrator, since the
dashboard reads study data and cannot delete it.

Undoing an exclusion removes the row rather than marking it undone. The absence of
a row is the default state, so there is nothing to record about a device nobody
excluded.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


async def _rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


async def excluded_ids(db: AsyncSession, model) -> set[str]:
    """Every excluded device on this platform.

    An absent table reads as nothing excluded rather than an error, so a
    deployment that predates the table exports exactly as it did before.
    """
    try:
        result = await db.execute(select(model.device_id))
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return set()
    return {str(row[0]) for row in result.all() if row[0]}


async def exclusions(db: AsyncSession, model) -> dict[str, dict]:
    """Each excluded device, with when it was excluded and why."""
    try:
        result = await db.execute(select(model).order_by(model.excluded_at.desc()))
        rows = result.scalars().all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {
        str(row.device_id): {
            "excluded_at": int(row.excluded_at or 0),
            "note": row.note or "",
        }
        for row in rows
    }


async def exclude(
    db: AsyncSession, model, device_id: str, excluded_at: int, note: str = ""
) -> dict | None:
    """Take a device out of the analysis, or revise the note on one already out.

    Idempotent: excluding a device twice is the same state as excluding it once,
    and a researcher correcting the reason should not be told the device is
    already excluded.
    """
    try:
        existing = await db.get(model, device_id)
        if existing is None:
            db.add(model(device_id=device_id, excluded_at=excluded_at, note=note))
        else:
            existing.note = note
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
        return None
    return {
        "device_id": device_id,
        "excluded_at": int(existing.excluded_at) if existing else excluded_at,
        "note": note,
    }


async def include(db: AsyncSession, model, device_id: str) -> bool:
    """Put a device back into the analysis.

    True when the device is now included, whether or not it was excluded before:
    the caller asked for a state, and it holds either way.
    """
    try:
        await db.execute(delete(model).where(model.device_id == device_id))
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
        return False
    return True


async def records_by_device(
    db: AsyncSession, count_model, device_ids: set[str]
) -> dict[str, int]:
    """How many records each of these devices holds, read from the count cache.

    The figure an exclusion actually costs. A researcher deciding whether to leave
    a participant out is deciding about an amount of data, and "exclude this phone"
    means very different things at two hundred rows and at two million.

    Summed over the cache rather than the data tables, so the answer is one grouped
    read of a small table instead of a `COUNT(*)` across sixty large ones.
    """
    if not device_ids:
        return {}
    try:
        rows = (
            await db.execute(
                select(count_model.device_id, func.sum(count_model.count))
                .where(count_model.device_id.in_(device_ids))
                .group_by(count_model.device_id)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {str(device_id): int(total or 0) for device_id, total in rows}
