"""How many records arrived, per table, per device, per hour.

`record_counts` holds totals, which answers "how much is there" and nothing
about *when* it arrived. The export dialog needs the count inside a chosen
period, and the coverage heatmap needs a cell per bucket; both are the same
question at different resolutions, and both are unanswerable from a total.

So this keeps one row per `(table, device, hour)` with the number of records in
it. An hour is the finest grain anything asks for: a day cell sums 24 rows and a
month cell sums its days, so one table serves the whole
year -> month -> day -> hour drill-down without precomputing a level.

Keyed by **table** rather than by sensor, for two reasons. Each table carries its
own `_id` sequence, so a watermark per table is the natural unit — a sensor
stored across two tables (`esm`, `wifi`) has two sequences and cannot share one,
which is why the sensor-keyed count cache excludes those sensors entirely. And a
builder that walks the tables rather than a registry covers a table added later
without anyone remembering to register it.

`last_id` rides on the row, so a table's watermark is `MAX(last_id)` for it, and
clearing the rollup clears its watermark: a rebuild starts from zero with nothing
else to reset.

A bucket is **recounted from the source** rather than added to. `_id` is
auto-increment, so two inserts can take 501 and 502 and commit in the other
order: a pass reading `MAX(_id)` between them records 502 and never looks below
it again, leaving 501 uncounted. Adding would carry that loss forever, since
nothing revisits a bucket once written. Recounting makes every pass
self-correcting — a bucket is whatever the source says it is now, so a row missed
that way is picked up as soon as anything else lands in its hour.

The watermark still decides *which* hours to recount, which is what keeps a pass
proportional to what arrived rather than to the table.

Timestamps are AWARE's epoch milliseconds, so bucketing is integer arithmetic on
them and lands in UTC. A display timezone is applied when a grid is drawn.
"""

from sqlalchemy import and_, case, column, func, select, table as sql_table, true
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import coverage

HOUR_MS = 60 * 60 * 1000

#: Dashboard-owned tables carry no study data and must not roll themselves up.
SKIP_TABLES = frozenset({"coverage_hourly", "record_counts"})

#: Buckets per upsert statement. Large enough that a backfill costs tens of round
#: trips rather than thousands, small enough to stay well inside a packet.
WRITE_CHUNK = 500


async def _rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


async def source_tables(db: AsyncSession, database: str) -> list[str]:
    """Every table holding timestamped study data, largest first."""
    tables = await coverage.timestamped_tables(db, database)
    return [name for name in tables if name not in SKIP_TABLES]


async def watermark_for(db: AsyncSession, model, table: str) -> int:
    """The highest `_id` already folded in for `table`."""
    try:
        highest = (
            await db.execute(
                select(func.coalesce(func.max(model.last_id), 0)).where(
                    model.table_name == table
                )
            )
        ).scalar()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return 0
    return int(highest or 0)


def _source(name: str):
    """The three columns this reads, on a table named at runtime.

    The builder walks whatever tables the database holds rather than a fixed set
    of models, so the source cannot be an ORM class. Every AWARE data table
    carries these three.
    """
    return sql_table(name, column("_id"), column("device_id"), column("timestamp"))


async def _new_rows_since(db: AsyncSession, source, watermark: int):
    """The oldest timestamp and highest `_id` among rows added since `watermark`.

    Answering this first means a table with nothing new costs one indexed look
    and no aggregation at all, which is the common case on every pass after the
    first.
    """
    source_id = source.c["_id"]
    return (
        await db.execute(
            select(
                func.min(source.c.timestamp).label("oldest"),
                func.max(source_id).label("highest_id"),
            ).where(source_id > watermark)
        )
    ).one()


async def _write(db: AsyncSession, model, rows: list[dict]) -> None:
    """Upsert the buckets, a chunk of rows per statement.

    One statement per bucket costs a round trip each, which is invisible at a
    few thousand and minutes of pure waiting at a few million.
    """
    for start in range(0, len(rows), WRITE_CHUNK):
        chunk = rows[start : start + WRITE_CHUNK]
        statement = mysql_insert(model).values(chunk)
        await db.execute(
            statement.on_duplicate_key_update(
                # Absolute, not additive: the bucket becomes what the source
                # says it holds.
                records=statement.inserted.records,
                # The watermark is read as MAX(last_id) for the table, so a
                # recounted bucket must never lower it.
                last_id=func.greatest(model.last_id, statement.inserted.last_id),
            )
        )


async def refresh_table(db: AsyncSession, model, database: str, table: str) -> int:
    """Recount every hour that `table` has received rows in since its watermark.

    Returns how many records those hours now hold. A table the database no
    longer has, or one without the columns this reads, is skipped rather than
    failing the whole pass.
    """
    watermark = await watermark_for(db, model, table)
    source = _source(table)
    source_id = source.c["_id"]
    bucket = func.floor(func.coalesce(source.c.timestamp, 0) / HOUR_MS) * HOUR_MS

    try:
        arrived = await _new_rows_since(db, source, watermark)
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return 0

    if arrived.highest_id is None:
        return 0

    # Recount from the oldest hour that received something, so the hours it
    # touched are rebuilt from the source rather than adjusted.
    oldest_hour = int((arrived.oldest or 0) // HOUR_MS * HOUR_MS)

    try:
        rows = (
            await db.execute(
                select(
                    source.c.device_id.label("device_id"),
                    bucket.label("hour_start"),
                    func.count().label("records"),
                    func.max(source_id).label("highest_id"),
                )
                .where(source.c.timestamp >= oldest_hour)
                .group_by(source.c.device_id, bucket)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return 0

    buckets = [
        {
            "table_name": table,
            "device_id": str(row.device_id),
            "hour_start": int(row.hour_start),
            "records": int(row.records),
            "last_id": int(row.highest_id),
        }
        for row in rows
        if row.device_id is not None and row.hour_start is not None
    ]
    if not buckets:
        return 0

    await _write(db, model, buckets)
    return sum(bucket["records"] for bucket in buckets)


async def refresh(db: AsyncSession, model, database: str) -> dict[str, int]:
    """One pass over every source table. Returns the records added per table.

    The first pass on an empty rollup has a watermark of zero everywhere, so it
    reads the whole history: the backfill is this, run once. The grouping happens
    in the database, so a table of millions of rows returns only its buckets.

    The returned figure is what the touched hours now hold, not what was added —
    a recount reports the total it wrote.
    """
    added: dict[str, int] = {}
    for table in await source_tables(db, database):
        counted = await refresh_table(db, model, database, table)
        if counted:
            added[table] = counted

    try:
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
        return {}
    return added


def _overlapping(model, window):
    """Conditions selecting the buckets a window touches.

    A bucket covers the hour beginning at `hour_start`, so a window that starts
    or ends part-way through one includes that whole hour. The figure is
    therefore hour-granular at its edges — which is what makes it cheap, and is
    the difference between reading a summary table and counting the rows
    themselves. Callers wanting an exact figure must count the source.
    """
    start, end = window
    conditions = []
    if start is not None:
        conditions.append(model.hour_start + HOUR_MS > start)
    if end is not None:
        conditions.append(model.hour_start <= end)
    return conditions


async def records_by_table(
    db: AsyncSession,
    model,
    window,
    tables=None,
    device_id: str | None = None,
    exclude=None,
    only=None,
) -> dict[str, int]:
    """How many records each table holds inside `window`, per the rollup.

    `tables` restricts the answer to a set of table names; `device_id` to one
    phone. A table with nothing in the window is absent rather than zero.

    `exclude` leaves a set of devices out, which is what turns this into the
    figure an export writes; `only` restricts to that same set, which is the
    figure the exclusion holds back. An empty `only` matches no device, so a
    study with nothing excluded holds nothing back.
    """
    query = select(model.table_name, func.sum(model.records).label("records"))
    for condition in _overlapping(model, window):
        query = query.where(condition)
    if tables is not None:
        query = query.where(model.table_name.in_(list(tables)))
    if device_id is not None:
        query = query.where(model.device_id == device_id)
    if exclude:
        query = query.where(model.device_id.not_in(list(exclude)))
    if only is not None:
        query = query.where(model.device_id.in_(list(only)))

    try:
        rows = (await db.execute(query.group_by(model.table_name))).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}

    return {
        str(row.table_name): int(row.records)
        for row in rows
        if row.table_name and row.records
    }


async def records_in(
    db: AsyncSession,
    model,
    window,
    tables=None,
    device_id: str | None = None,
    exclude=None,
    only=None,
) -> int:
    """The total the rollup reports for `window`, across `tables`."""
    return sum(
        (
            await records_by_table(
                db, model, window, tables, device_id, exclude, only
            )
        ).values()
    )


async def devices_with_records(
    db: AsyncSession, model, window, tables=None, device_id=None, only=None
) -> int:
    """How many distinct devices the rollup shows records for in `window`.

    Counted rather than derived from a device list, so the figure reported beside
    a record total covers the same window and tables that total does: a device
    excluded from the study but silent in the chosen period holds nothing back
    from it.
    """
    query = select(func.count(func.distinct(model.device_id)))
    for condition in _overlapping(model, window):
        query = query.where(condition)
    query = query.where(model.records > 0)
    if tables is not None:
        query = query.where(model.table_name.in_(list(tables)))
    if device_id is not None:
        query = query.where(model.device_id == device_id)
    if only is not None:
        query = query.where(model.device_id.in_(list(only)))

    try:
        counted = (await db.execute(query)).scalar()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return 0
    return int(counted or 0)


async def records_for_windows(
    db: AsyncSession, model, windows: list, tables=None, exclude=None
) -> list[int]:
    """How many records each of several windows holds, in one read.

    A period control offers ten windows at once and needs a figure for each of
    them before the researcher has chosen anything. Asked one at a time that is
    ten aggregates; asked as a sum per window it is one, over the same rows.

    Returns a total per window, positionally. A window with no bounds counts
    everything, which is what the explicit `all time` choice means.
    """
    if not windows:
        return []

    columns = []
    for index, window in enumerate(windows):
        conditions = _overlapping(model, window)
        matched = and_(*conditions) if conditions else true()
        columns.append(
            func.coalesce(func.sum(case((matched, model.records), else_=0)), 0).label(
                f"w{index}"
            )
        )

    query = select(*columns)
    if tables is not None:
        query = query.where(model.table_name.in_(list(tables)))
    if exclude:
        query = query.where(model.device_id.not_in(list(exclude)))

    try:
        row = (await db.execute(query)).one()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return [0] * len(windows)

    return [int(value or 0) for value in row]


async def reset(db: AsyncSession, model) -> None:
    """Empty the rollup so the next pass rebuilds it from zero."""
    try:
        await db.execute(model.__table__.delete())
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
