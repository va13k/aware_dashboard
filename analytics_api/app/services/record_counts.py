"""Exact per-(sensor, device) record counts, cached and maintained incrementally.

Live ``COUNT(*)`` is O(rows) and the device page and manifest need dozens per
request. Instead the counts live in a dashboard-owned ``record_counts`` table
(one per platform DB) and are refreshed off the request path: each refresh
advances a per-sensor watermark on the source table's auto-increment ``_id`` and
adds only the rows inserted since, so a refresh costs a scan proportional to
*ingest*, not to table size, and reads are O(1) lookups.

Correctness rests on ``_id`` being monotonic and the source tables being
append-only. ``_id`` (not ``timestamp``) is the watermark because timestamps
arrive out of order. If rows are ever purged, ``reset`` clears the cache so the
next refresh rebuilds it from zero.
"""

import contextlib

from sqlalchemy import func, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

#: Names the lock every refresher competes for. MySQL advisory locks are held per
#: connection and scoped to the whole server, so one lock covers both platform
#: schemas: they live on the same server.
REFRESH_LOCK = "aware_record_counts_refresh"

#: What an Android insert with no `device_id` lands as, the column defaulting to
#: the empty string. The cache keeps this internal row so its `_id` can advance
#: the sensor watermark, but every public total filters it out to match exports.
ORPHAN_DEVICE = ""


@contextlib.asynccontextmanager
async def single_writer(engine, lock_name: str = REFRESH_LOCK):
    """Yields True to the one caller holding the refresh lock, False to the rest.

    The counts are folded in additively (``count = count + d``), so two refreshes
    reading the same watermark would each add the same rows and leave a total
    above the truth that only a reset can correct. Serialising on a lock the
    database owns covers every refresher at once: the scheduled one, a run
    started by hand, and the HTTP endpoint.

    The lock lives on the connection that took it, so this holds one open for the
    whole block and releases the lock as it closes.
    """
    async with engine.connect() as connection:
        acquired = (
            await connection.execute(
                text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}
            )
        ).scalar()
        try:
            yield acquired == 1
        finally:
            if acquired == 1:
                await connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name}
                )


async def _rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except SQLAlchemyError:
        pass


async def refresh(db: AsyncSession, count_model, source_models: dict) -> dict:
    """Fold rows added since the last refresh into the cache.

    ``source_models`` maps a sensor slug to its ORM model. Returns a
    ``{sensor: rows_added}`` map for the sensors that gained rows. A missing
    source table is skipped (per-deployment sensors vary).
    """
    added: dict[str, int] = {}
    for sensor, model in source_models.items():
        try:
            watermark = (
                await db.execute(
                    select(func.coalesce(func.max(count_model.last_id), 0)).where(
                        count_model.sensor == sensor
                    )
                )
            ).scalar() or 0
            rows = (
                await db.execute(
                    select(
                        model.device_id,
                        func.count().label("d"),
                        func.max(model._id).label("m"),
                        func.max(model.timestamp).label("ts"),
                    )
                    .where(model._id > watermark)
                    .group_by(model.device_id)
                )
            ).all()
        except (ProgrammingError, OperationalError, SQLAlchemyError):
            await _rollback(db)
            continue

        gained = 0
        for device_id, d, m, ts in rows:
            if device_id is None:
                continue
            d, m = int(d), int(m)
            ts = float(ts) if ts is not None else 0.0
            stmt = mysql_insert(count_model).values(
                sensor=sensor, device_id=device_id, count=d, last_id=m, last_ts=ts
            )
            stmt = stmt.on_duplicate_key_update(
                count=count_model.count + d,
                last_id=m,
                # Never let last_ts regress if a batch arrives slightly out of order.
                last_ts=func.greatest(count_model.last_ts, ts),
            )
            await db.execute(stmt)
            # Keep an internal orphan row so an orphan-only batch still advances
            # this sensor's watermark. Without it, the refresher rescans the same
            # bad rows every minute forever. Public readers filter the row below.
            if device_id != ORPHAN_DEVICE:
                gained += d
        if gained:
            added[sensor] = gained

    try:
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
    return added


async def counts_for_device(db: AsyncSession, count_model, device_id: str) -> dict:
    """``{sensor: {count, last_ts, last_id}}`` for one device — one query that
    lets the device page render every tile (count + last-seen) with no per-sensor
    lookups, and fetch a single latest payload by ``last_id`` (a PK lookup)."""
    try:
        rows = (
            await db.execute(
                select(
                    count_model.sensor,
                    count_model.count,
                    count_model.last_ts,
                    count_model.last_id,
                ).where(count_model.device_id == device_id)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {
        sensor: {"count": int(count), "last_ts": float(last_ts), "last_id": int(last_id)}
        for sensor, count, last_ts, last_id in rows
    }


async def sensor_totals(db: AsyncSession, count_model) -> dict:
    """``{sensor: (total_count, devices_with_data)}`` across all devices."""
    try:
        rows = (
            await db.execute(
                select(
                    count_model.sensor,
                    func.sum(count_model.count),
                    func.count(),
                )
                .where(
                    count_model.count > 0,
                    count_model.device_id != ORPHAN_DEVICE,
                )
                .group_by(count_model.sensor)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {sensor: (int(total or 0), int(devices)) for sensor, total, devices in rows}


async def newest_timestamp(db: AsyncSession, count_model) -> float | None:
    """The newest row this database holds, across every sensor and device.

    The cache already carries `last_ts` per (sensor, device), so this is one
    aggregate over a small table rather than a `MAX(timestamp)` per data table.
    It anchors the periods a period control offers, which is why it is read here
    and not from the hourly rollup: the rollup would round it down to the top of
    its hour, and a period counted back from that would end early.
    """
    try:
        newest = (
            await db.execute(
                select(func.max(count_model.last_ts)).where(
                    count_model.last_ts > 0,
                    count_model.device_id != ORPHAN_DEVICE,
                )
            )
        ).scalar()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return None
    return float(newest) if newest else None


async def reset(db: AsyncSession, count_model) -> None:
    """Drop the whole cache so the next refresh rebuilds it (post-purge)."""
    try:
        await db.execute(count_model.__table__.delete())
        await db.commit()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
