"""What periods the databases actually hold data for.

The export page offers a period to back up, and an offer is only worth making if
something would come out of it. Answering that has to stay cheap on a database
holding a study's worth of rows, which the schema allows: every data table
carries ``KEY time_device (timestamp, device_id)``, so ``MIN``/``MAX`` over the
whole table are index seeks rather than scans, and "is there anything between
these two instants" is a seek that stops at the first hit.

Periods are offered against two anchors, because on a running study they answer
different questions. Anchored to the newest row, "the last day" is the last day
the phones reported and always returns something. Anchored to the clock, it is
the last day in real time, which is empty when nothing has come in — and that
emptiness is exactly what the page needs to know before offering it.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * HOUR_MS

#: The periods offered, shortest first. A month and a year are the usual
#: approximations — this picks a window to export, not a calendar boundary.
PERIODS = (
    ("hour", "Hour", HOUR_MS),
    ("day", "Day", DAY_MS),
    ("week", "Week", 7 * DAY_MS),
    ("month", "Month", 30 * DAY_MS),
    ("year", "Year", 365 * DAY_MS),
)

#: Anchored to the newest stored row, or to the clock.
DATA_ANCHOR = "data"
CLOCK_ANCHOR = "now"

#: Rows default `timestamp` to 0, and a phone that never set one would otherwise
#: drag the reported span back to 1970.
EPOCH_FLOOR = 1


async def _rollback(db) -> None:
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


async def timestamped_tables(db, database: str) -> list[str]:
    """Data tables in `database`, largest first.

    Size order is what makes an existence probe cheap in the common case: the
    biggest table is the one most likely to answer "yes" on the first look.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT t.TABLE_NAME FROM information_schema.TABLES t "
                    "JOIN information_schema.COLUMNS c "
                    "  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME "
                    "WHERE t.TABLE_SCHEMA = :schema AND t.TABLE_TYPE = 'BASE TABLE' "
                    "  AND c.COLUMN_NAME = 'timestamp' "
                    "ORDER BY t.DATA_LENGTH DESC"
                ),
                {"schema": database},
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return []
    return [row[0] for row in rows]


async def span(db, database: str, tables: list[str]) -> tuple[float | None, float | None]:
    """The oldest and newest timestamp stored anywhere in `database`."""
    oldest = newest = None
    for table in tables:
        try:
            row = (
                await db.execute(
                    text(
                        f"SELECT MIN(timestamp), MAX(timestamp) FROM `{database}`.`{table}` "
                        f"WHERE timestamp >= {EPOCH_FLOOR}"
                    )
                )
            ).first()
        except (ProgrammingError, OperationalError, SQLAlchemyError):
            await _rollback(db)
            continue
        if row is None:
            continue
        low, high = row
        if low is not None and (oldest is None or low < oldest):
            oldest = float(low)
        if high is not None and (newest is None or high > newest):
            newest = float(high)
    return oldest, newest


async def has_rows(db, database: str, tables: list[str], start: float, end: float) -> bool:
    """Whether any table holds a row inside ``[start, end]``.

    Stops at the first table that does, so a populated window costs one seek.
    """
    for table in tables:
        try:
            found = (
                await db.execute(
                    text(
                        f"SELECT 1 FROM `{database}`.`{table}` "
                        "WHERE timestamp >= :start AND timestamp <= :end LIMIT 1"
                    ),
                    {"start": start, "end": end},
                )
            ).first()
        except (ProgrammingError, OperationalError, SQLAlchemyError):
            await _rollback(db)
            continue
        if found is not None:
            return True
    return False


def windows(newest: float | None, now_ms: float) -> list[dict]:
    """Every period on offer, as a concrete ``[from, to]`` pair.

    A period whose anchor is missing — no stored data to count back from — is
    returned with no bounds, which reads as unavailable.
    """
    offered = []
    for anchor, end in ((DATA_ANCHOR, newest), (CLOCK_ANCHOR, now_ms)):
        for key, label, length in PERIODS:
            offered.append(
                {
                    "key": f"{anchor}:{key}",
                    "anchor": anchor,
                    "period": key,
                    "label": label,
                    "from": (end - length) if end is not None else None,
                    "to": end,
                    "available": False,
                }
            )
    return offered
