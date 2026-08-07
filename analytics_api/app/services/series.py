"""Server-side bucketed sensor aggregation.

A raw ``LIMIT`` slice of a wide time window is unrepresentative: a high-rate
sensor (e.g. a 50 Hz accelerometer) holds millions of rows over a week, and the
newest 1500 of them cover only seconds. Instead we aggregate the window into a
fixed number of evenly-spaced buckets so point density stays consistent for any
range from an hour to a year.

Each bucket is ``{t, avg, lo, hi, n}``: the bucket-start timestamp (ms), the
mean/min/max of the sensor's value column over that slice, and the raw row
count. Event sensors with no numeric value pass ``value_expr=None`` and get
count-only buckets (``avg/lo/hi`` are ``None``).

``timestamp`` is a Double epoch in milliseconds (AWARE convention), so bucketing
is plain integer math on it — no DATETIME conversion.
"""

import time

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_BUCKETS = 1500
MAX_BUCKETS = 3000

# The widest window any single-device data pull (series or CSV export) may span.
# AWARE ``timestamp`` is an epoch-**milliseconds** double, so this is expressed
# in ms. We keep no ``(device_id, timestamp)`` secondary index (see the plan),
# so the only thing bounding a scan is the time window: an unbounded "all time"
# request on a 50 Hz sensor would range-scan every device across all history.
# Capping the window at one year keeps the existing ``(timestamp, device_id)``
# index range-scan bounded while still covering any realistic study period.
MAX_WINDOW_MS = 365 * 24 * 60 * 60 * 1000


def _now_ms() -> float:
    return time.time() * 1000


def clamp_window(
    from_ts: float | None,
    to_ts: float | None,
    now_ms: float | None = None,
) -> tuple[float, float]:
    """Resolve a possibly-open ``[from_ts, to_ts]`` request into a bounded window.

    Enforces the query strategy for on-demand, index-only scans:

    - a missing ``to_ts`` anchors to *now*;
    - a missing ``from_ts`` never means "all history" — it becomes
      ``to_ts - MAX_WINDOW_MS``;
    - a reversed pair is swapped;
    - any window wider than ``MAX_WINDOW_MS`` is trimmed from the older
      (``from_ts``) end, keeping the most recent year.

    Both bounds are returned as floats so callers can always apply a
    ``timestamp >= from_ts AND timestamp <= to_ts`` range predicate.
    """
    if now_ms is None:
        now_ms = _now_ms()
    to = float(to_ts) if to_ts is not None else float(now_ms)
    frm = float(from_ts) if from_ts is not None else to - MAX_WINDOW_MS
    if to < frm:
        frm, to = to, frm
    if to - frm > MAX_WINDOW_MS:
        frm = to - MAX_WINDOW_MS
    return frm, to


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


async def bucketed_series(
    db: AsyncSession,
    model,
    value_expr,
    device_id: str,
    from_ts: float | None,
    to_ts: float | None,
    buckets: int = DEFAULT_BUCKETS,
) -> list[dict]:
    """Aggregate ``model`` rows for ``device_id`` in ``[from_ts, to_ts]`` into
    ``buckets`` evenly-spaced buckets. Missing bounds are filled from the
    device's own min/max timestamp so an "all time" request still buckets.

    ``value_expr`` is a SQLAlchemy expression evaluating to the row's numeric
    value, or ``None`` for count-only buckets. A missing table (per-deployment)
    is swallowed and returns ``[]``, matching the detail endpoint's behaviour.
    """
    buckets = max(1, min(buckets, MAX_BUCKETS))

    try:
        if from_ts is None or to_ts is None:
            bounds = (
                await db.execute(
                    select(
                        func.min(model.timestamp), func.max(model.timestamp)
                    ).where(model.device_id == device_id)
                )
            ).one()
            min_ts, max_ts = bounds
            if min_ts is None:
                return []
            # Anchor open bounds to the device's own data extent, then clamp so
            # an "all time" span wider than a year keeps only the recent year.
            from_ts, to_ts = clamp_window(
                from_ts if from_ts is not None else float(min_ts),
                to_ts if to_ts is not None else float(max_ts),
            )
        else:
            from_ts, to_ts = clamp_window(from_ts, to_ts)

        span = to_ts - from_ts
        width = span / buckets if span > 0 else 1.0

        bucket_index = func.floor((model.timestamp - from_ts) / width)
        columns = [bucket_index.label("bucket"), func.count().label("n")]
        if value_expr is not None:
            columns += [
                func.avg(value_expr).label("avg"),
                func.min(value_expr).label("lo"),
                func.max(value_expr).label("hi"),
            ]

        query = (
            select(*columns)
            .where(model.device_id == device_id)
            .where(model.timestamp >= from_ts)
            .where(model.timestamp <= to_ts)
            .group_by(bucket_index)
            .order_by(bucket_index)
        )
        rows = (await db.execute(query)).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return []

    result = []
    for row in rows:
        mapping = row._mapping
        bucket = int(mapping["bucket"])
        result.append(
            {
                "t": from_ts + bucket * width,
                "avg": _as_float(mapping.get("avg")) if value_expr is not None else None,
                "lo": _as_float(mapping.get("lo")) if value_expr is not None else None,
                "hi": _as_float(mapping.get("hi")) if value_expr is not None else None,
                "n": int(mapping["n"]),
            }
        )
    return result
