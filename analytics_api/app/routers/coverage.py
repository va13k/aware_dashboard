"""What a period holds, asked before anything is downloaded.

An export dialog has one question to answer while the researcher is still
choosing: how much is in there. It has to be answered on the request path, for
any period, over both platforms — so it cannot count rows, and the count cache
cannot help because it holds totals with no notion of when.

The hourly rollup is what it reads instead (services/coverage_rollup.py). That
makes the answer a grouped read of a small table rather than an aggregate over
sixty large ones, and it reaches ``esm`` and ``wifi`` — sensors stored across two
tables each, and therefore absent from the sensor-keyed cache entirely.

Totals are hour-granular at the window's edges, because a bucket is a whole hour.
That is the trade the rollup exists to make: a figure shown beside a period
control wants to be right about its magnitude and instant to produce, and a
window landing mid-hour counts the hour it lands in.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_android_db, get_ios_db
from app.models import (
    AndroidCoverageHourly,
    AndroidRecordCount,
    IosCoverageHourly,
    IosRecordCount,
)
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.services import coverage, coverage_rollup, record_counts, sensor_tables

router = APIRouter(prefix="/coverage", tags=["coverage"])

PLATFORMS = ("android", "ios")

_EXPORT_MODELS_FOR = {"android": ANDROID_EXPORT_MODELS, "ios": IOS_EXPORT_MODELS}
_ROLLUP_FOR = {"android": AndroidCoverageHourly, "ios": IosCoverageHourly}
_COUNTS_FOR = {"android": AndroidRecordCount, "ios": IosRecordCount}


def _requested_platforms(platform: str | None) -> tuple[str, ...]:
    """Which platforms to answer for. Absent means both."""
    if platform is None or platform == "all":
        return PLATFORMS
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")
    return (platform,)


def _window(from_ts: float | None, to_ts: float | None) -> tuple:
    """The chosen period. A reversed pair reads as the range it means."""
    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        return (to_ts, from_ts)
    return (from_ts, to_ts)


async def _platform_counts(
    db: AsyncSession, platform: str, window: tuple, sensor: str | None
) -> tuple[int, dict[str, int]]:
    """One platform's total for the window, and its split by sensor.

    The rollup answers per table, so the sensors are recovered on the way back
    out. A table this platform's export does not claim is dropped rather than
    counted under a guess — it is bookkeeping or a sensor the API does not serve,
    and either way not something a dialog can offer to download.
    """
    export_models = _EXPORT_MODELS_FOR[platform]
    by_table = sensor_tables.sensor_by_table(export_models)

    wanted = None
    if sensor is not None:
        wanted = sensor_tables.tables_for(export_models, sensor)
        if not wanted:
            return 0, {}

    counted = await coverage_rollup.records_by_table(
        db, _ROLLUP_FOR[platform], window, wanted
    )

    by_sensor: dict[str, int] = {}
    for table, records in counted.items():
        name = by_table.get(table)
        if name is None:
            continue
        by_sensor[name] = by_sensor.get(name, 0) + records

    return sum(by_sensor.values()), by_sensor


async def records_across(sessions: dict, window: tuple) -> list[int]:
    """What one window holds on each platform, in the order `sessions` gives."""
    return [
        (await coverage_rollup.records_for_windows(db, _ROLLUP_FOR[name], [window]))[0]
        for name, db in sessions.items()
    ]


async def offered_windows(sessions: dict, newest: float | None, now_ms: float) -> list[dict]:
    """Every period on offer, each carrying what it actually holds.

    One contract for both the export dialogs and the backup page, so the two
    cannot come to disagree about which periods are worth offering.

    `available` used to be settled by probing the data tables for a single row
    per window. That is cheap when a window has data and worst when it does not
    — it walks every table before concluding nothing is there, which is exactly
    the case the page needs in order to grey the period out. Read from the
    rollup instead, all windows in one aggregate per platform, and the answer
    arrives with a record count rather than just a yes.
    """
    offered = coverage.windows(newest, now_ms)

    # A period whose anchor is missing has no bounds to ask about, and reads as
    # unavailable however much the study holds.
    askable = [entry for entry in offered if entry["from"] is not None]
    if not askable:
        return offered

    bounds = [(entry["from"], entry["to"]) for entry in askable]
    totals = {name: [0] * len(bounds) for name in sessions}
    for name, db in sessions.items():
        totals[name] = await coverage_rollup.records_for_windows(
            db, _ROLLUP_FOR[name], bounds
        )

    for index, entry in enumerate(askable):
        per_platform = {name: totals[name][index] for name in sessions}
        entry["records"] = sum(per_platform.values())
        entry["platforms"] = per_platform
        entry["available"] = entry["records"] > 0

    for entry in offered:
        entry.setdefault("records", 0)
        entry.setdefault("platforms", {name: 0 for name in sessions})

    return offered


@router.get("/windows")
async def coverage_windows(
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """The periods a researcher may pick, and what each one holds.

    A relative period is returned as the absolute pair it resolves to, because a
    choice whose starting point is invisible makes an export impossible to
    reproduce afterwards.
    """
    now_ms = time.time() * 1000
    sessions = {"android": android_db, "ios": ios_db}
    newest = await _newest_stored(sessions)

    return {
        "now": now_ms,
        "newest": newest,
        "windows": await offered_windows(sessions, newest, now_ms),
        "hour_granular": True,
    }


async def _newest_stored(sessions: dict) -> float | None:
    """The newest row either platform holds, from the count cache.

    Exact rather than hour-granular, because it anchors half the periods on
    offer: read from `record_counts.last_ts` instead of the rollup, which would
    round the anchor down to the top of the hour.
    """
    newest = None
    for name, db in sessions.items():
        stamp = await record_counts.newest_timestamp(db, _COUNTS_FOR[name])
        if stamp is not None and (newest is None or stamp > newest):
            newest = stamp
    return newest


@router.get("/counts")
async def coverage_counts(
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    platform: str | None = Query(None),
    sensor: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """How many records a period holds, in total and per sensor.

    Both ends are optional and inclusive: omitting them asks about everything
    stored, which is the ``all time`` choice the export dialog offers explicitly
    rather than as a silent default.

    ``platform`` narrows to one side, ``sensor`` to one card. Both are reported
    per platform as well as summed, because a sensor card spans the two and
    offers all-platforms / iPhone / Android as its second question.
    """
    window = _window(from_ts, to_ts)
    wanted = _requested_platforms(platform)
    sessions = {"android": android_db, "ios": ios_db}

    totals: dict[str, int] = {}
    sensors: dict[str, dict[str, int]] = {}
    for name in wanted:
        total, by_sensor = await _platform_counts(sessions[name], name, window, sensor)
        totals[name] = total
        sensors[name] = by_sensor

    return {
        "from": window[0],
        "to": window[1],
        "total": sum(totals.values()),
        "platforms": totals,
        "sensors": sensors,
        # What a dialog needs to decide whether the download is worth offering:
        # an empty period is a button that should not be pressed.
        "available": sum(totals.values()) > 0,
        # Buckets are whole hours, so a window landing part-way through one
        # counts it. Said plainly rather than left for a caller to discover by
        # comparing this with a row count.
        "hour_granular": True,
    }
