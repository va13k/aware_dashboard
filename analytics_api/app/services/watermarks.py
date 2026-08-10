"""Newest stored timestamp per ``(table, device_id)`` — the merge import's
answer to "do we already have this row?".

No AWARE table has a unique key over its data, so a merge cannot let MySQL
reject duplicates for it. What the schema does give is ``KEY time_device
(timestamp, device_id)`` on every stream, and the dashboard already keeps
``record_counts.last_ts`` — exactly ``MAX(timestamp)`` per ``(sensor, device)``,
maintained incrementally. Reading it turns the per-row duplicate test into a
dict lookup, so a merge needs no staging copy and no probe into the target.

The cache covers the sensor streams in the export registry. The handful of
remaining tables (study, device and log bookkeeping) are small and get a live
``GROUP BY``, which the ``time_device`` index serves without touching rows.
"""

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


def table_names(sources: dict) -> dict[str, str]:
    """``{sensor slug: table name}`` for the record-count sources. Several iOS
    slugs share one model, and they collapse onto the same table here."""
    return {slug: model.__tablename__ for slug, model in sources.items()}


async def _cached(
    db: AsyncSession, count_model, sources: dict
) -> tuple[dict[str, dict[str, float]], set[str]]:
    """Watermarks the count cache knows, and the tables it cannot answer for.

    ``last_ts`` joined ``record_counts`` after the first release, so rows written
    before it read 0, and the incremental refresh only rewrites a row when new
    data arrives for that sensor and device — a phone that stopped uploading
    keeps its 0 indefinitely. A 0 means "not recorded", not "the epoch": read as
    a watermark it would admit every row the table has ever held.

    One unusable entry condemns the whole table to the live path. Trusting the
    rest would filter some devices and wave the others straight through, which
    is the mixture that quietly duplicates data.
    """
    slug_to_table = table_names(sources)
    try:
        rows = (
            await db.execute(
                select(count_model.sensor, count_model.device_id, count_model.last_ts)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await db.rollback()
        return {}, set()

    by_table: dict[str, dict[str, float]] = {}
    unusable: set[str] = set()
    for sensor, device_id, last_ts in rows:
        table = slug_to_table.get(sensor)
        if table is None:
            continue
        if last_ts is None or last_ts <= 0:
            unusable.add(table)
            continue
        devices = by_table.setdefault(table, {})
        newest = devices.get(device_id)
        if newest is None or last_ts > newest:
            devices[device_id] = float(last_ts)
    return by_table, unusable


async def _mergeable_tables(db: AsyncSession, database: str) -> list[str]:
    """Tables in `database` carrying both columns the merge test needs."""
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT TABLE_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = :schema AND COLUMN_NAME IN ('device_id', 'timestamp') "
                    "GROUP BY TABLE_NAME HAVING COUNT(DISTINCT COLUMN_NAME) = 2"
                ),
                {"schema": database},
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await db.rollback()
        return []
    return [row[0] for row in rows]


async def _live(db: AsyncSession, database: str, table: str) -> dict[str, float]:
    """``MAX(timestamp)`` per device, straight from the table."""
    try:
        rows = (
            await db.execute(
                text(
                    f"SELECT device_id, MAX(timestamp) FROM `{database}`.`{table}` "
                    "GROUP BY device_id"
                )
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await db.rollback()
        return {}
    return {
        str(device_id): float(newest)
        for device_id, newest in rows
        if device_id is not None and newest is not None
    }


async def build(
    db: AsyncSession,
    database: str,
    count_model,
    sources: dict,
    progress=None,
) -> dict[tuple[str, str], dict[str, float]]:
    """Every watermark for one platform database, keyed ``(database, table)``.

    `progress` is called with a short phase string per table so a long build
    stays visible on the backup page.
    """
    cached, unusable = await _cached(db, count_model, sources)
    watermarks: dict[tuple[str, str], dict[str, float]] = {
        (database, table): devices
        for table, devices in cached.items()
        if table not in unusable
    }

    for table in await _mergeable_tables(db, database):
        if table in cached and table not in unusable:
            continue
        if progress:
            progress(f"Reading {database}.{table} watermarks")
        devices = await _live(db, database, table)
        if devices:
            watermarks[(database, table)] = devices

    return watermarks
