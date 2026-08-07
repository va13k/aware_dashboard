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

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


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
                    )
                    .where(model._id > watermark)
                    .group_by(model.device_id)
                )
            ).all()
        except (ProgrammingError, OperationalError, SQLAlchemyError):
            await _rollback(db)
            continue

        gained = 0
        for device_id, d, m in rows:
            if device_id is None:
                continue
            d, m = int(d), int(m)
            stmt = mysql_insert(count_model).values(
                sensor=sensor, device_id=device_id, count=d, last_id=m
            )
            stmt = stmt.on_duplicate_key_update(
                count=count_model.count + d, last_id=m
            )
            await db.execute(stmt)
            gained += d
        if gained:
            added[sensor] = gained

    try:
        await db.commit()
    except SQLAlchemyError:
        await _rollback(db)
    return added


async def counts_for_device(db: AsyncSession, count_model, device_id: str) -> dict:
    """``{sensor: count}`` for one device — one query for a whole device page."""
    try:
        rows = (
            await db.execute(
                select(count_model.sensor, count_model.count).where(
                    count_model.device_id == device_id
                )
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {sensor: int(count) for sensor, count in rows}


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
                .where(count_model.count > 0)
                .group_by(count_model.sensor)
            )
        ).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
        return {}
    return {sensor: (int(total or 0), int(devices)) for sensor, total, devices in rows}


async def reset(db: AsyncSession, count_model) -> None:
    """Drop the whole cache so the next refresh rebuilds it (post-purge)."""
    try:
        await db.execute(count_model.__table__.delete())
        await db.commit()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        await _rollback(db)
