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

import csv
import io
import time
import zipfile
from datetime import datetime, timezone as utc_timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_android_db, get_ios_db
from app.models import (
    AndroidCoverageHourly,
    AndroidDeviceExclusion,
    AndroidDeviceEnrolment,
    AndroidRecordCount,
    IosCoverageHourly,
    IosDeviceExclusion,
    IosRecordCount,
)
from app.routers.android import _EXPORT_MODELS as ANDROID_EXPORT_MODELS
from app.routers.ios import _EXPORT_MODELS as IOS_EXPORT_MODELS
from app.services import (
    coverage,
    coverage_matrix,
    coverage_rollup,
    coverage_workbook,
    enrolment,
    exclusions,
    export_size,
    record_counts,
    sensor_rates,
    sensor_requirements,
    sensor_tables,
    study_config,
)

router = APIRouter(prefix="/coverage", tags=["coverage"])

PLATFORMS = ("android", "ios")

_EXPORT_MODELS_FOR = {"android": ANDROID_EXPORT_MODELS, "ios": IOS_EXPORT_MODELS}
_ROLLUP_FOR = {"android": AndroidCoverageHourly, "ios": IosCoverageHourly}
_COUNTS_FOR = {"android": AndroidRecordCount, "ios": IosRecordCount}
_EXCLUSION_FOR = {"android": AndroidDeviceExclusion, "ios": IosDeviceExclusion}
#: Only Android reports enrolment; an iPhone keeps its study state on the phone.
_ENROLMENT_FOR = {"android": AndroidDeviceEnrolment, "ios": None}


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
    db: AsyncSession,
    platform: str,
    window: tuple,
    sensor: str | None,
    device: str | None = None,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """One platform's total for the window, its split by sensor, and by table.

    The per-table figures come back too, because a size estimate is per table:
    a million magnetometer rows and a million bluetooth rows are not the same
    download.

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
            return 0, {}, {}

    counted = await coverage_rollup.records_by_table(
        db, _ROLLUP_FOR[platform], window, wanted, device
    )

    by_sensor: dict[str, int] = {}
    for table, records in counted.items():
        name = by_table.get(table)
        if name is None:
            continue
        by_sensor[name] = by_sensor.get(name, 0) + records

    return sum(by_sensor.values()), by_sensor, counted


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


def _level_and_anchor(level: str, anchor: float | None) -> tuple[str, float]:
    """The requested resolution, and the instant that picks the span it covers."""
    if level not in coverage_matrix.LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown level: {level}. One of {', '.join(coverage_matrix.LEVELS)}.",
        )
    return level, time.time() * 1000 if anchor is None else anchor


def _observable_required(platform: str) -> list[str]:
    """Sensors the study requires *and* this API can see rows for.

    A required setting whose stream has no table behind it — a scheduler, a
    transport setting — cannot contribute to "how much of what we asked for
    arrived", and leaving it in the denominator would hold every cell below full
    for a reason no grid could show.
    """
    requirements = sensor_requirements.study_requirements()[platform]
    export_models = _EXPORT_MODELS_FOR[platform]
    return sorted(
        entry.sensor_key
        for entry in requirements.sensors
        if entry.required and sensor_tables.tables_for(export_models, entry.sensor_key)
    )


def _rates_for(platform: str) -> dict:
    return sensor_rates.study_rates()[platform]


async def _expectation_windows(
    db: AsyncSession, platform: str, now_ms: float
) -> dict[str, list[dict]]:
    """When each device was expected to be sending, per device.

    Android has this on record: `device_enrolment` holds a window per join, and
    the gap between two of them is time nothing was expected. iOS has nothing to
    derive from — the study state never leaves the phone — so a window is opened
    at the device's first record instead, which is the same fallback the Android
    derivation uses for a phone that never reported joining. It cannot show a
    withdrawal, so an iPhone's row runs to the present.
    """
    model = _ENROLMENT_FOR[platform]
    windows = {}
    if model is not None:
        windows = await enrolment.stored_windows(db, model)

    first_seen = await enrolment.first_record_by_device(db, _ROLLUP_FOR[platform])
    for device, first_hour in first_seen.items():
        if not windows.get(device):
            windows[device] = [
                {
                    "joined_at": int(first_hour),
                    "left_at": None,
                    "join_source": enrolment.FIRST_DATA,
                    "left_source": None,
                }
            ]
    return windows


def _sensor_counts_by_device(
    platform: str, counted: dict, bucket_count: int
) -> dict[str, dict[str, list[int]]]:
    """Fold the rollup's per-table rows up into per-sensor rows.

    The rollup is keyed by table because a table owns its own `_id` sequence; a
    grid is read by sensor. `esm` and `wifi` are the reason this is a sum rather
    than a rename: each is stored across two tables, and a row of the grid means
    the sensor, not one of its tables.
    """
    by_device: dict[str, dict[str, list[int]]] = {}
    by_table = sensor_tables.sensor_by_table(_EXPORT_MODELS_FOR[platform])

    for (device, table), buckets in counted.items():
        sensor = by_table.get(table)
        if sensor is None:
            continue
        per_sensor = by_device.setdefault(device, {})
        running = per_sensor.setdefault(sensor, [0] * bucket_count)
        for index, value in enumerate(buckets):
            running[index] += value
    return by_device


async def _platform_grid(
    db: AsyncSession,
    platform: str,
    buckets: list,
    sensor: str | None,
    now_ms: float,
) -> list[dict]:
    """One platform's rows of the study grid: a device per row."""
    export_models = _EXPORT_MODELS_FOR[platform]

    tables = None
    if sensor is not None:
        tables = sensor_tables.tables_for(export_models, sensor)
        if not tables:
            return []

    counted = await coverage_matrix.bucketed_by_table(
        db, _ROLLUP_FOR[platform], buckets, tables
    )
    windows = await _expectation_windows(db, platform, now_ms)
    by_device = _sensor_counts_by_device(platform, counted, len(buckets))
    # A row the exports leave out has to say so here. The grid is where a
    # researcher reads what the study holds, and a device silently missing from an
    # archive they later download is the discrepancy this exists to prevent.
    excluded = await exclusions.exclusions(db, _EXCLUSION_FOR[platform])

    rates = _rates_for(platform)
    required = _observable_required(platform)
    rate = None if sensor is None else sensor_rates.resolved(rates, sensor)

    rows = []
    # A device with a window but no data still belongs on the grid: an empty row
    # inside an enrolment is the clearest thing the view can show.
    for device in sorted(set(by_device) | set(windows)):
        per_sensor = by_device.get(device, {})
        device_windows = windows.get(device)
        cells = []
        for index, bucket in enumerate(buckets):
            hours = coverage_matrix.covered_hours(bucket, device_windows, now_ms)
            if sensor is not None:
                records = per_sensor.get(sensor, [0] * len(buckets))[index]
                cells.append(coverage_matrix.cell(records, bucket, hours, rate))
            else:
                present = {
                    key: counts[index] for key, counts in per_sensor.items()
                }
                cells.append(
                    coverage_matrix.aggregate_cell(present, required, bucket, hours)
                )

        rows.append(
            {
                "device_id": device,
                "platform": platform,
                "enrolment_windows": device_windows or [],
                "cells": cells,
                "records": sum(cell.get("records", 0) for cell in cells),
                # Present when a researcher has left this device out of the
                # analysis. The cells still say what arrived: what was collected is
                # a fact, and the exclusion is a decision about it.
                "excluded": excluded.get(device),
            }
        )
    return rows


def _grid_scale(rows: list[dict]) -> int:
    """The busiest cell on the grid, for a sequential colour scale.

    Returned rather than left to the client so every platform on one grid is
    shaded against the same ceiling — two rows of the same colour then hold the
    same amount of data, which is the whole claim a heatmap makes.
    """
    return max(
        (cell.get("records", 0) for row in rows for cell in row["cells"]),
        default=0,
    )


async def _excluded_summary(
    sessions: dict, wanted: tuple | list
) -> dict:
    """Who is left out of the analysis, and how much data that is.

    The count is what makes the decision legible. A grid marking two rows as
    excluded says nothing about whether the exports are missing a rounding error or
    a third of the study, and that is the difference a researcher needs.

    All-time rather than the visible span: the exports the exclusion governs are
    not bounded by whatever the grid happens to be showing.
    """
    devices: list[dict] = []
    for name in wanted:
        db = sessions[name]
        excluded = await exclusions.exclusions(db, _EXCLUSION_FOR[name])
        if not excluded:
            continue
        totals = await exclusions.records_by_device(
            db, _COUNTS_FOR[name], set(excluded)
        )
        for device_id, entry in excluded.items():
            devices.append(
                {
                    "device_id": device_id,
                    "platform": name,
                    "records": totals.get(device_id, 0),
                    **entry,
                }
            )
    return {
        "devices": len(devices),
        "records": sum(entry["records"] for entry in devices),
        "rows": sorted(devices, key=lambda entry: entry["records"], reverse=True),
    }


@router.get("/study")
async def study_coverage(
    level: str = Query(coverage_matrix.DAY),
    anchor: float | None = Query(None),
    platform: str | None = Query(None),
    sensor: str | None = Query(None),
    tz: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """The study grid: a device per row, a bucket per column.

    `level` names the bucket width and `anchor` any instant inside the span it
    covers, so `month` draws the anchor's year as twelve columns, `day` draws its
    month, and `hour` draws its day. Clicking a column is the same request at the
    next level down with that column's start as the anchor.

    With `sensor` given a cell is that sensor's coverage, judged against the rate
    the study config asks for. Without one it is how many of the required sensors
    reported at all, which is the question a grid of every sensor at once can
    actually answer.

    `tz` is the timezone the buckets are cut in. The rollup stores UTC hours, so
    changing it re-cuts the same stored data rather than re-reading anything.
    """
    resolved_level, anchor_ms = _level_and_anchor(level, anchor)
    wanted = _requested_platforms(platform)
    zone = coverage_matrix.resolve_timezone(tz)
    buckets = coverage_matrix.buckets_for(resolved_level, anchor_ms, zone)
    now_ms = time.time() * 1000

    sessions = {"android": android_db, "ios": ios_db}
    rows: list[dict] = []
    for name in wanted:
        rows.extend(
            await _platform_grid(sessions[name], name, buckets, sensor, now_ms)
        )

    start, end = coverage_matrix.span_of(buckets)
    return {
        "level": resolved_level,
        "drills_into": coverage_matrix.DRILLS_INTO[resolved_level],
        "anchor": anchor_ms,
        "timezone": str(zone),
        "from": start,
        "to": end,
        "sensor": sensor,
        "platforms": list(wanted),
        "buckets": [
            {"key": bucket.key, "label": bucket.label, "from": bucket.start, "to": bucket.end}
            for bucket in buckets
        ],
        "rows": rows,
        "max_records": _grid_scale(rows),
        "required_sensors": {name: _observable_required(name) for name in wanted},
        "hour_granular": True,
        # What the exports leave out, so the grid and an archive downloaded from it
        # cannot disagree without saying so.
        "excluded": await _excluded_summary(sessions, wanted),
    }


@router.get("/device/{platform}/{device_id}")
async def device_coverage(
    platform: str,
    device_id: str,
    level: str = Query(coverage_matrix.DAY),
    anchor: float | None = Query(None),
    tz: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """One phone's grid: a sensor per row, the same buckets as the study grid.

    Answers "is this phone collecting everything it should", which the study grid
    cannot show for a single device — there, one row is one device across every
    sensor at once.

    Every sensor the study requires gets a row whether it reported or not, since a
    required sensor absent from the grid is the finding rather than an omission.
    """
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    resolved_level, anchor_ms = _level_and_anchor(level, anchor)
    zone = coverage_matrix.resolve_timezone(tz)
    buckets = coverage_matrix.buckets_for(resolved_level, anchor_ms, zone)
    now_ms = time.time() * 1000

    db = android_db if platform == "android" else ios_db
    windows = (await _expectation_windows(db, platform, now_ms)).get(device_id)
    rows = await _device_grid_rows(db, platform, device_id, buckets, now_ms)

    start, end = coverage_matrix.span_of(buckets)
    return {
        "platform": platform,
        "device_id": device_id,
        "level": resolved_level,
        "drills_into": coverage_matrix.DRILLS_INTO[resolved_level],
        "anchor": anchor_ms,
        "timezone": str(zone),
        "from": start,
        "to": end,
        "enrolment_windows": windows or [],
        "buckets": _bucket_payload(buckets),
        "rows": rows,
        "max_records": _grid_scale(rows),
        "hour_granular": True,
    }


async def _device_grid_rows(
    db: AsyncSession,
    platform: str,
    device_id: str,
    buckets: list,
    now_ms: float,
) -> list[dict]:
    """One phone's rows: a sensor per row, judged against its configured rate.

    Shared by the endpoint and the workbook, so the spreadsheet a researcher
    downloads holds the same rows the screen showed them.
    """
    counted = await coverage_matrix.bucketed_by_table(
        db, _ROLLUP_FOR[platform], buckets, None, device_id
    )
    windows = (await _expectation_windows(db, platform, now_ms)).get(device_id)
    per_sensor = _sensor_counts_by_device(platform, counted, len(buckets)).get(
        device_id, {}
    )

    rates = _rates_for(platform)
    required = set(_observable_required(platform))

    rows = []
    for sensor in sorted(required | set(per_sensor)):
        counts = per_sensor.get(sensor, [0] * len(buckets))
        rate = sensor_rates.resolved(rates, sensor)
        cells = [
            coverage_matrix.cell(
                counts[index],
                bucket,
                coverage_matrix.covered_hours(bucket, windows, now_ms),
                rate,
            )
            for index, bucket in enumerate(buckets)
        ]
        rows.append(
            {
                "sensor": sensor,
                "required": sensor in required,
                "cells": cells,
                "records": sum(counts),
                "expected_per_hour": (
                    round(rate.per_hour, 4) if rate.comparable else None
                ),
                "basis": rate.basis,
            }
        )
    return rows


#: Hour columns one matrix export may carry. Two months of them is already a
#: spreadsheet nothing opens comfortably, and the request is a mistake past that
#: rather than a large study.
MAX_MATRIX_HOURS = 24 * 62

#: How a covered hour is written. `presence` reproduces the reference
#: spreadsheet — 1 or blank — and `counts` writes the record count instead, which
#: is the same matrix with the magnitude kept.
PRESENCE = "presence"
COUNTS = "counts"


def _matrix_hours(window: tuple, zone) -> list[coverage_matrix.Bucket]:
    """One column per hour across the window, aligned to the display timezone."""
    start, end = window
    if start is None or end is None:
        raise HTTPException(
            status_code=422,
            detail="A matrix export needs both from_ts and to_ts.",
        )
    if start > end:
        start, end = end, start

    first = int(start // coverage_matrix.HOUR_MS * coverage_matrix.HOUR_MS)
    count = int((end - first) // coverage_matrix.HOUR_MS) + 1
    if count > MAX_MATRIX_HOURS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"That window is {count} hours; a matrix export carries at most "
                f"{MAX_MATRIX_HOURS}. Narrow the period."
            ),
        )

    labels = coverage_matrix.hour_labels(first, count, zone)
    return [
        coverage_matrix.Bucket(
            key=label,
            label=label,
            start=first + index * coverage_matrix.HOUR_MS,
            end=first + (index + 1) * coverage_matrix.HOUR_MS,
        )
        for index, label in enumerate(labels)
    ]


def _matrix_sheet(
    buckets: list[coverage_matrix.Bucket],
    per_device: dict[str, list[int]],
    values: str,
    zone,
) -> bytes:
    """One sensor's sheet: a device per row, an hour per column.

    The reference spreadsheet's layout — device, the first hour it covers, then a
    mark per hour, then the total of them — because the point of producing this is
    that it can be diffed against that file.
    """
    sink = io.StringIO()
    writer = csv.writer(sink)
    writer.writerow(
        ["device_id", "start", *[bucket.label for bucket in buckets], "covered_hours"]
    )

    for device in sorted(per_device):
        counts = per_device[device]
        covered = [index for index, value in enumerate(counts) if value > 0]
        start = (
            coverage_matrix.hour_labels(buckets[covered[0]].start, 1, zone)[0]
            if covered
            else ""
        )
        marks = [
            ("" if value <= 0 else (value if values == COUNTS else 1))
            for value in counts
        ]
        writer.writerow([device, start, *marks, len(covered)])

    return sink.getvalue().encode("utf-8")


def _bucket_payload(buckets: list) -> list[dict]:
    return [
        {"key": bucket.key, "label": bucket.label, "from": bucket.start, "to": bucket.end}
        for bucket in buckets
    ]


def _workbook_name(scope: str, level: str, buckets: list) -> str:
    return f"coverage-{scope}-{level}-{_stamp(buckets[0].start)}.xlsx"


def _workbook_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/study.xlsx")
async def study_coverage_workbook(
    level: str = Query(coverage_matrix.DAY),
    anchor: float | None = Query(None),
    platform: str | None = Query(None),
    sensor: str | None = Query(None),
    tz: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """The study grid as a spreadsheet, exactly as it is drawn on screen.

    Takes the same parameters as `/coverage/study` and builds the same rows and
    buckets from them, so the file holds the view the researcher was looking at
    rather than a fixed layout of its own: the level's buckets across, a device per
    row, the record count in each cell with the colour its band gives it, and a
    total down every row and across every column.
    """
    resolved_level, anchor_ms = _level_and_anchor(level, anchor)
    wanted = _requested_platforms(platform)
    zone = coverage_matrix.resolve_timezone(tz)
    buckets = coverage_matrix.buckets_for(resolved_level, anchor_ms, zone)
    now_ms = time.time() * 1000

    sessions = {"android": android_db, "ios": ios_db}
    rows: list[dict] = []
    for name in wanted:
        rows.extend(
            await _platform_grid(sessions[name], name, buckets, sensor, now_ms)
        )

    start, end = coverage_matrix.span_of(buckets)
    sheet_rows = [
        {"label": f"{row['device_id']} ({row['platform']})", "cells": row["cells"]}
        for row in rows
    ]
    content = coverage_workbook.build(
        buckets=_bucket_payload(buckets),
        rows=sheet_rows,
        row_header="Device",
        about=[
            ("Study", _study_title()),
            ("Level", f"{resolved_level} buckets"),
            ("From", _iso(start)),
            ("To", _iso(end)),
            ("Timezone", str(zone)),
            ("Platforms", ", ".join(wanted)),
            (
                "Sensor",
                sensor if sensor else "all required sensors (cells count reporting sensors)",
            ),
            ("Devices", len(sheet_rows)),
        ],
    )
    return _workbook_response(
        content, _workbook_name("study", resolved_level, buckets)
    )


# A path segment of its own rather than a `.xlsx` suffix: `{device_id}` would
# otherwise match "phone-a.xlsx" on the grid route above, leaving which handler
# answers to depend on the order they happen to be declared in.
@router.get("/device/{platform}/{device_id}/workbook.xlsx")
async def device_coverage_workbook(
    platform: str,
    device_id: str,
    level: str = Query(coverage_matrix.DAY),
    anchor: float | None = Query(None),
    tz: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """One phone's grid as a spreadsheet: a sensor per row, the same buckets."""
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    resolved_level, anchor_ms = _level_and_anchor(level, anchor)
    zone = coverage_matrix.resolve_timezone(tz)
    buckets = coverage_matrix.buckets_for(resolved_level, anchor_ms, zone)
    now_ms = time.time() * 1000

    db = android_db if platform == "android" else ios_db
    rows = await _device_grid_rows(db, platform, device_id, buckets, now_ms)

    start, end = coverage_matrix.span_of(buckets)
    sheet_rows = [
        {
            "label": row["sensor"] + ("" if row["required"] else " (extra)"),
            "cells": row["cells"],
        }
        for row in rows
    ]
    content = coverage_workbook.build(
        buckets=_bucket_payload(buckets),
        rows=sheet_rows,
        row_header="Sensor",
        about=[
            ("Study", _study_title()),
            ("Device", device_id),
            ("Platform", platform),
            ("Level", f"{resolved_level} buckets"),
            ("From", _iso(start)),
            ("To", _iso(end)),
            ("Timezone", str(zone)),
            ("Sensors", len(sheet_rows)),
        ],
    )
    return _workbook_response(
        content,
        f"coverage-{_safe_name(device_id)}-{resolved_level}-{_stamp(start)}.xlsx",
    )


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value)[:40]


def _study_title() -> str:
    deployed = study_config.load_deployed_config()
    title = (deployed.summary.get("study_title") if deployed else None) or "AWARE study"
    return str(title)


@router.get("/matrix")
async def coverage_matrix_export(
    from_ts: float = Query(...),
    to_ts: float = Query(...),
    platform: str | None = Query(None),
    tz: str | None = Query(None),
    values: str = Query(PRESENCE),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """The whole grid as files: one CSV per sensor, devices down, hours across.

    The reference this reproduces is a workbook of one sheet per sensor. A sheet
    becomes a CSV inside a ZIP, which is the shape every other export here takes
    and needs no spreadsheet library on the server; a reader opens the archive and
    gets one tab per file.

    Built in memory rather than streamed, because the size is bounded by the grid
    and not by the data: a sensor's sheet is one row per device however many
    millions of records those hours hold.
    """
    if values not in (PRESENCE, COUNTS):
        raise HTTPException(
            status_code=422, detail=f"values must be {PRESENCE} or {COUNTS}"
        )

    wanted = _requested_platforms(platform)
    zone = coverage_matrix.resolve_timezone(tz)
    buckets = _matrix_hours((from_ts, to_ts), zone)
    sessions = {"android": android_db, "ios": ios_db}

    archive = io.BytesIO()
    written = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in wanted:
            counted = await coverage_matrix.bucketed_by_table(
                sessions[name], _ROLLUP_FOR[name], buckets
            )
            by_device = _sensor_counts_by_device(name, counted, len(buckets))

            # Transposed: the archive is read a sensor at a time, so a sensor no
            # phone reported gets no file rather than a sheet of empty rows.
            by_sensor: dict[str, dict[str, list[int]]] = {}
            for device, sensors in by_device.items():
                for sensor, counts in sensors.items():
                    by_sensor.setdefault(sensor, {})[device] = counts

            for sensor in sorted(by_sensor):
                member = f"{name}/{sensor.replace('/', '-')}.csv"
                bundle.writestr(
                    member, _matrix_sheet(buckets, by_sensor[sensor], values, zone)
                )
                written += 1

        bundle.writestr(
            "README.txt",
            (
                "Coverage matrix, one file per sensor.\n\n"
                f"Window: {_iso(buckets[0].start)} to {_iso(buckets[-1].end)}\n"
                f"Timezone: {zone}\n"
                f"Hour columns: {len(buckets)}\n"
                f"Sensor files: {written}\n"
                f"Values: {values}"
                + (
                    " (1 where the hour holds at least one record)\n"
                    if values == PRESENCE
                    else " (records per hour)\n"
                )
                + "\nA column is a whole hour, counted from the rollup. An hour is\n"
                "attributed to the column its start falls in.\n"
                + (
                    ""
                    if written
                    else "\nNo sensor reported anything inside this window, so the\n"
                    "archive holds this note and nothing else. Pick a period the\n"
                    "study has data for.\n"
                )
            ).encode("utf-8"),
        )

    stamp = _stamp(buckets[0].start)
    filename = f"coverage-matrix-{stamp}-{len(buckets)}h.zip"
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Sheet-Count": str(written),
        },
    )


def _iso(milliseconds: float) -> str:
    return datetime.fromtimestamp(
        milliseconds / 1000, tz=utc_timezone.utc
    ).isoformat()


def _stamp(milliseconds: float) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=utc_timezone.utc).strftime(
        "%Y%m%d-%H%M"
    )


@router.get("/counts")
async def coverage_counts(
    from_ts: float | None = Query(None),
    to_ts: float | None = Query(None),
    platform: str | None = Query(None),
    sensor: str | None = Query(None),
    device: str | None = Query(None),
    android_db: AsyncSession = Depends(get_android_db),
    ios_db: AsyncSession = Depends(get_ios_db),
):
    """How many records a period holds, in total and per sensor.

    Both ends are optional and inclusive: omitting them asks about everything
    stored, which is the ``all time`` choice the export dialog offers explicitly
    rather than as a silent default.

    ``platform`` narrows to one side, ``sensor`` to one card, ``device`` to one
    phone. They are reported per platform as well as summed, because a sensor
    card spans the two and offers all-platforms / iPhone / Android as its second
    question — a device belongs to one platform and needs no such choice.
    """
    window = _window(from_ts, to_ts)
    wanted = _requested_platforms(platform)
    sessions = {"android": android_db, "ios": ios_db}

    databases = {"android": "aware_android", "ios": "aware_ios"}

    totals: dict[str, int] = {}
    sensors: dict[str, dict[str, int]] = {}
    estimated = 0
    for name in wanted:
        db = sessions[name]
        total, by_sensor, by_table = await _platform_counts(
            db, name, window, sensor, device
        )
        totals[name] = total
        sensors[name] = by_sensor
        if by_table:
            per_row = await export_size.bytes_per_row(db, databases[name])
            estimated += export_size.estimate(by_table, per_row)

    return {
        "from": window[0],
        "to": window[1],
        "total": sum(totals.values()),
        "platforms": totals,
        "sensors": sensors,
        # Roughly what the download will weigh. A magnitude, not a promise —
        # see services/export_size.py for how far it can be out.
        "estimated_bytes": estimated,
        # What a dialog needs to decide whether the download is worth offering:
        # an empty period is a button that should not be pressed.
        "available": sum(totals.values()) > 0,
        # Buckets are whole hours, so a window landing part-way through one
        # counts it. Said plainly rather than left for a caller to discover by
        # comparing this with a row count.
        "hour_granular": True,
    }
