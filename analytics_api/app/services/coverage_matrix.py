"""The coverage grid: one row per device or sensor, one column per bucket.

Three resolutions, one query shape. A month cell is a sum over its days, a day
cell a sum over its hours, and the hour is what the rollup stores — so the
year -> month -> day drill-down is the same read at a different bucket width
rather than three features, and nothing needs precomputing per level.

Buckets are built in the display timezone and the rollup is grouped into them in
one statement, a `SUM(CASE ...)` column per bucket, which is the idiom
`coverage_rollup.records_for_windows` already uses for the period control. That
keeps a grid to one round trip per platform and returns at most
devices x tables rows however long the span is: a year at month resolution costs
the same twelve columns as a day costs twenty-four.

A bucket carries a whole rollup hour, assigned by where that hour *starts*. For
the timezones whose offset is a whole number of hours — most of them — local
bucket edges land exactly on rollup hour edges and the grid is exact. For the
half- and quarter-hour offsets (India, Nepal, parts of Australia) an hour is
attributed to the local bucket its start falls in, so an edge bucket can carry up
to one hour from its neighbour. That is the same hour-granularity trade the
export dialog's totals make, and for the same reason: the rollup's finest grain
is an hour.

**What a cell says** rests on two things the data tables cannot answer. Whether
anything was expected comes from the enrolment windows (services/enrolment.py) —
before a device joined and after it left, an empty bucket is not a gap. And how
much was expected comes from the study config (services/sensor_rates.py). A
bucket only partly inside an enrolment window expects only its covered part,
which is what stops the joining hour and the leaving hour reading as failures.

Not every stream has an amount to be judged on. An event sensor has no configured
rate, and a gated one has a rate the phone then filters against — both arrive
here carrying no comparison, and their buckets say whether data came rather than
whether enough did.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

HOUR_MS = 60 * 60 * 1000

#: Bucket widths, named after the bucket rather than the span it covers: `month`
#: draws a year as twelve columns, `day` draws a month, `hour` draws a day.
MONTH = "month"
DAY = "day"
HOUR = "hour"
LEVELS = (MONTH, DAY, HOUR)

#: The next level down, for a caller following a click.
DRILLS_INTO = {MONTH: DAY, DAY: HOUR, HOUR: None}

#: What a cell says.
NOT_EXPECTED = "not_expected"
REPORTING = "reporting"
UNDER = "under"
MISSING = "missing"
#: Data arrived but the config offers nothing to judge the amount against: an
#: event sensor, or a rate setting the config does not carry.
PRESENT = "present"

#: A bucket at or above this fraction of its expectation reads as reporting
#: rather than under-reporting. The line is "at or above what the configured
#: frequency implies", with room for the two places a whole-hour bucket is
#: unavoidably approximate: a sampling loop drifts by a sample or two an hour, and
#: an hour is attributed to one bucket even when the enrolment window it belongs
#: to opens part-way through it.
REPORTING_RATIO = 0.9

#: Where a bucket sits against its expectation, as a reader sees it. `state` says
#: which side of the configured rate a bucket fell on; a band splits that finer,
#: far enough short and far enough over each earning their own reading.
BAND_BLANK = "blank"
BAND_NONE = "none"
BAND_SHORT = "short"
BAND_MODERATE = "moderate"
BAND_EXPECTED = "expected"
BAND_OVER = "over"
#: Records arrived with no configured rate to weigh them against.
BAND_UNJUDGED = "unjudged"

#: Below this share of the expectation, a shortfall is its own band.
SHORT_BELOW = 0.5
#: Above this multiple of the expectation, a bucket reads as far over.
FAR_OVER = 2


def band_for(state: str, records: int, expected: float | None) -> str:
    """Which band a classified cell falls in.

    Derived from `state` rather than recomputed from the ratio, so the boundary
    between reporting and under-reporting is stated once (`REPORTING_RATIO`) and
    the bands only split what it has already decided.

    Served to every reader — the grid on screen and the workbook a researcher
    downloads — so a colour cannot mean one thing in the browser and another in
    the spreadsheet.
    """
    if state == NOT_EXPECTED:
        return BAND_BLANK
    if state == MISSING:
        return BAND_NONE
    if state == PRESENT:
        return BAND_UNJUDGED

    share = None if not expected else records / expected
    if state == UNDER:
        return BAND_SHORT if share is not None and share < SHORT_BELOW else BAND_MODERATE
    return BAND_OVER if share is not None and share > FAR_OVER else BAND_EXPECTED


def aggregate_band(reporting: int, required: int) -> str:
    """Which band an all-sensors cell falls in, by the share that reported.

    The share is a fraction of what the study asked for and cannot exceed it, so
    this scale has no `over`.
    """
    if not required or not reporting:
        return BAND_NONE
    share = reporting / required
    if share < SHORT_BELOW:
        return BAND_SHORT
    return BAND_MODERATE if share < 1 else BAND_EXPECTED


@dataclass(frozen=True)
class Bucket:
    """One column: a half-open range `[start, end)` in epoch milliseconds."""

    key: str
    label: str
    start: int
    end: int

    @property
    def hours(self) -> float:
        return (self.end - self.start) / HOUR_MS


def resolve_timezone(name: str | None) -> ZoneInfo:
    """The display timezone, falling back to UTC rather than failing.

    A timezone arrives from a browser control, so an unknown name is a bad
    request rather than something to raise on: the grid is still readable in UTC,
    and the response says which zone it was actually drawn in.
    """
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _local(anchor_ms: float, zone: ZoneInfo) -> datetime:
    return datetime.fromtimestamp(anchor_ms / 1000, tz=dt_timezone.utc).astimezone(zone)


def buckets_for(level: str, anchor_ms: float, zone: ZoneInfo) -> list[Bucket]:
    """The columns of one grid: the months of the anchor's year, the days of its
    month, or the hours of its day.

    Boundaries are built as local wall-clock instants and converted back, so a
    day containing a daylight-saving change spans 23 or 25 hours and gets a column
    for each hour the local clock actually passed through.
    """
    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")

    here = _local(anchor_ms, zone)

    if level == MONTH:
        edges = [
            datetime(here.year, month, 1, tzinfo=zone) for month in range(1, 13)
        ] + [datetime(here.year + 1, 1, 1, tzinfo=zone)]
        return [
            Bucket(
                key=f"{here.year:04d}-{index + 1:02d}",
                label=calendar.month_abbr[index + 1],
                start=_ms(edges[index]),
                end=_ms(edges[index + 1]),
            )
            for index in range(12)
        ]

    if level == DAY:
        days = calendar.monthrange(here.year, here.month)[1]
        edges = [
            datetime(here.year, here.month, day, tzinfo=zone)
            for day in range(1, days + 1)
        ] + [_month_after(here, zone)]
        return [
            Bucket(
                key=f"{here.year:04d}-{here.month:02d}-{index + 1:02d}",
                label=str(index + 1),
                start=_ms(edges[index]),
                end=_ms(edges[index + 1]),
            )
            for index in range(days)
        ]

    midnight = datetime(here.year, here.month, here.day, tzinfo=zone)
    edges = [midnight + timedelta(hours=step) for step in range(25)]
    return [
        Bucket(
            key=f"{here.year:04d}-{here.month:02d}-{here.day:02d}T{index:02d}",
            label=f"{index:02d}",
            start=_ms(edges[index]),
            end=_ms(edges[index + 1]),
        )
        for index in range(24)
        # A local day losing an hour to daylight saving has 23 real columns.
        if _ms(edges[index]) < _ms(edges[index + 1])
    ]


def _month_after(here: datetime, zone: ZoneInfo) -> datetime:
    if here.month == 12:
        return datetime(here.year + 1, 1, 1, tzinfo=zone)
    return datetime(here.year, here.month + 1, 1, tzinfo=zone)


def hour_labels(first_hour: int, count: int, zone: ZoneInfo) -> list[str]:
    """`count` consecutive hour columns from `first_hour`, labelled locally.

    For the matrix export, where the columns run across an arbitrary window
    rather than within one calendar day, so a label has to carry its date.
    """
    return [
        datetime.fromtimestamp(
            (first_hour + step * HOUR_MS) / 1000, tz=dt_timezone.utc
        )
        .astimezone(zone)
        .strftime("%Y-%m-%d %H:00")
        for step in range(count)
    ]


def span_of(buckets: list[Bucket]) -> tuple[int, int]:
    """The whole grid's range, for bounding the read."""
    if not buckets:
        return 0, 0
    return buckets[0].start, buckets[-1].end


async def bucketed_by_table(
    db: AsyncSession,
    model,
    buckets: list[Bucket],
    tables: list[str] | None = None,
    device_id: str | None = None,
) -> dict[tuple[str, str], list[int]]:
    """Records per `(device, table)` per bucket, in one statement.

    Keyed by table because the rollup is: a caller wanting sensors folds the
    tables back up itself, which is also what lets one read serve both a
    single-sensor grid and the all-sensors aggregate.

    An hour is counted in the bucket its start falls in, so the columns partition
    the span and no record is counted twice.
    """
    if not buckets:
        return {}

    columns = [
        func.coalesce(
            func.sum(
                case(
                    (
                        (model.hour_start >= bucket.start)
                        & (model.hour_start < bucket.end),
                        model.records,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label(f"b{index}")
        for index, bucket in enumerate(buckets)
    ]

    start, end = span_of(buckets)
    query = (
        select(model.device_id, model.table_name, *columns)
        .where(model.hour_start >= start)
        .where(model.hour_start < end)
        .group_by(model.device_id, model.table_name)
    )
    if tables is not None:
        if not tables:
            return {}
        query = query.where(model.table_name.in_(list(tables)))
    if device_id is not None:
        query = query.where(model.device_id == device_id)

    try:
        rows = (await db.execute(query)).all()
    except (ProgrammingError, OperationalError, SQLAlchemyError):
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return {}

    counted: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        device = str(row[0] or "")
        table = str(row[1] or "")
        if not device or not table:
            continue
        counted[(device, table)] = [int(value or 0) for value in row[2:]]
    return counted


def covered_hours(bucket: Bucket, windows: list[dict] | None, now_ms: float) -> float:
    """How much of `bucket` the device was enrolled for, in hours.

    Zero means nothing was expected: the bucket sits entirely before the device
    joined, inside a gap between two enrolments, or after it left. A part-covered
    bucket is what the joining and leaving hours are, and scaling the expectation
    by this is what keeps them from reading as failures.

    A device with no windows at all is treated as never enrolled. The caller
    decides whether that is the truth — an Android phone that left no join trace —
    or a platform that cannot report enrolment, and supplies a fallback window.
    """
    if not windows:
        return 0.0

    overlap = 0
    for window in windows:
        start = window.get("joined_at")
        if start is None:
            continue
        end = window.get("left_at")
        end = now_ms if end is None else end
        low = max(int(start), bucket.start)
        high = min(int(end), bucket.end)
        if high > low:
            overlap += high - low
    return overlap / HOUR_MS


def classify(records: int, expected: float | None, comparable: bool) -> str:
    """What one cell says, given what arrived and what was expected.

    `comparable` is true where the config carries a rate to measure against.
    Elsewhere — an event sensor, a setting the config leaves out — presence is the
    whole claim available, so a bucket holding records reads `present`, and
    `reporting` stays reserved for a count actually compared with an expectation.
    """
    if not comparable or expected is None or expected <= 0:
        return PRESENT if records > 0 else MISSING
    if records <= 0:
        return MISSING
    return REPORTING if records >= expected * REPORTING_RATIO else UNDER


def cell(
    records: int,
    bucket: Bucket,
    hours: float,
    rate,
) -> dict:
    """One cell of a single-sensor grid.

    Carries the expectation alongside the count, because a colour on its own does
    not say what it was judged against — and for a sensor whose configured rate
    and delivered rate differ by orders of magnitude, that is the number the
    researcher needs to see before believing the colour.

    A figure the count is not comparable with is still carried, as a bound: a
    gated sensor's rate says what the hour could have held at most, which is worth
    reading beside what it did hold even though nothing is claimed about the gap.
    """
    if hours <= 0:
        # Nothing was asked for in this bucket, and something arrived anyway: a
        # phone still uploading after its enrolment closed. What arrived is a fact
        # and what was expected is an interpretation, so the count is shown as
        # unjudged rather than painted as an empty bucket -- a withdrawn
        # participant still sending data is exactly what a researcher must see.
        if records > 0:
            return {
                "state": PRESENT,
                "band": BAND_UNJUDGED,
                "records": records,
                "hours": 0,
            }
        return {
            "state": NOT_EXPECTED,
            "band": BAND_BLANK,
            "records": records,
            "hours": 0,
        }

    expected = rate.per_hour * hours if rate.per_hour else None
    state = classify(records, expected, rate.comparable)

    return {
        "state": state,
        "band": band_for(state, records, expected),
        "records": records,
        "hours": round(hours, 4),
        "expected": None if expected is None else round(expected, 2),
        "basis": rate.basis,
        # A scan sensor's figure bounds the scans, not the rows they yield, so a
        # count above it is not evidence the scan is healthy.
        "floor": rate.is_floor,
        # A gated sensor's figure bounds the count from above: the phone discards
        # samples before writing them, so arriving under it is what it does.
        "ceiling": rate.is_ceiling,
    }


def aggregate_cell(
    per_sensor: dict[str, int],
    required: list[str],
    bucket: Bucket,
    hours: float,
) -> dict:
    """One cell of the all-sensors grid: how much of what was asked for arrived.

    The fraction counts sensors reporting anything at all rather than sensors
    reporting enough, because the aggregate answers "did we get what we asked
    for" across streams whose expectations are not comparable with each other.
    Selecting a sensor is how the amount is examined.
    """
    if hours <= 0:
        # Same as a single sensor's cell: sensors reporting outside every window
        # are counted and left unjudged, since the fraction would be measured
        # against a list of sensors nothing was asked of.
        arriving = sum(1 for count in per_sensor.values() if count > 0)
        if arriving > 0:
            return {
                "state": PRESENT,
                "band": BAND_UNJUDGED,
                "reporting": arriving,
                "required": len(required),
            }
        return {
            "state": NOT_EXPECTED,
            "band": BAND_BLANK,
            "reporting": 0,
            "required": len(required),
        }

    reporting = sum(1 for key in required if per_sensor.get(key, 0) > 0)
    total = len(required)
    return {
        "state": MISSING if reporting == 0 else PRESENT,
        "band": aggregate_band(reporting, total),
        "reporting": reporting,
        "required": total,
        "fraction": None if not total else round(reporting / total, 4),
        "records": sum(per_sensor.values()),
        "hours": round(hours, 4),
    }
