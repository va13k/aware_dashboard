"""The coverage grid against a real MySQL, row by row.

What the fast tests cannot establish is whether the grid agrees with the tables
it claims to summarise. Every cell is a `SUM(CASE ...)` over the rollup, which is
itself a `GROUP BY` over a floor division of a timestamp — two layers of
arithmetic the database performs, and a stand-in session would only confirm the
calls were made.

Three things are checked against the source directly, because each is silent when
wrong and each would produce a grid that looks entirely plausible:

- a row lands in the hour it belongs to, including one written on the boundary
  and one written a millisecond before it;
- the columns partition the span, so summing a grid returns the same figure as
  counting the rows, and a day cell equals the sum of its hours;
- a non-UTC display timezone re-cuts the same rows rather than losing or
  duplicating any.

This is the mechanically checkable half of the reference-spreadsheet diff: that
file encodes presence per device per hour, which is what the matrix export writes
and what these assert against a `GROUP BY` written independently here.

The endpoints are called directly rather than through a test client, as the other
integration tests here do — a client runs the app in an event loop of its own, and
the sessions these build belong to this one.

Slow enough to be opt-in: `pytest -m integration`.
"""

import csv
import io
import zipfile
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidCoverageHourly
from app.routers import coverage as coverage_router
from app.services import coverage_matrix, coverage_rollup

pytestmark = pytest.mark.integration

DEVICE = "phone-a"
HOUR = coverage_rollup.HOUR_MS
#: 5 March 2026, 00:00 UTC — a round hour in the past, so an enrolment window
#: left open covers the whole day the grid is drawn over.
DAY = 1_772_668_800_000


@pytest_asyncio.fixture
async def deployment(clean_databases):
    """A live Android database, and sessions onto it and an empty iOS one."""
    android = create_async_engine(clean_databases.url("aware_android"))
    ios = create_async_engine(clean_databases.url("aware_ios"))
    yield clean_databases, (
        async_sessionmaker(android, class_=AsyncSession, expire_on_commit=False),
        async_sessionmaker(ios, class_=AsyncSession, expire_on_commit=False),
    )
    await android.dispose()
    await ios.dispose()


def seed(server, timestamps, device=DEVICE):
    """Rows into battery, which every grid in this file reads."""
    values = ",".join(f"({ts},'{device}',1,1,1)" for ts in timestamps)
    server.run(
        "INSERT INTO battery (timestamp, device_id, battery_status, battery_level, "
        f"battery_scale) VALUES {values}",
        "aware_android",
    )


def enrol(server, joined_at, device=DEVICE):
    server.run(
        "INSERT INTO device_enrolment (device_id, joined_at, join_source) VALUES "
        f"('{device}',{joined_at},'study_event')",
        "aware_android",
    )


def source_counts(server, start, end) -> dict[int, int]:
    """What the table itself holds per UTC hour, for the grid to be diffed to.

    Grouped by a statement written here rather than read from the rollup, so the
    assertion has an answer arrived at independently of the thing under test.
    """
    output = server.run(
        "SELECT FLOOR(timestamp / 3600000) * 3600000 AS h, COUNT(*) "
        f"FROM battery WHERE timestamp >= {start} AND timestamp < {end} "
        "GROUP BY h ORDER BY h",
        "aware_android",
    )
    counted = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        hour, count = line.split("\t")
        counted[int(hour)] = int(count)
    return counted


async def build_rollup(sessions):
    android, _ = sessions
    async with android() as db:
        await coverage_rollup.refresh(db, AndroidCoverageHourly, "aware_android")


async def study_grid(sessions, level="hour", anchor=DAY, tz="UTC", sensor="battery"):
    android, ios = sessions
    async with android() as android_db, ios() as ios_db:
        return await coverage_router.study_coverage(
            level=level,
            anchor=anchor,
            platform="android",
            sensor=sensor,
            tz=tz,
            android_db=android_db,
            ios_db=ios_db,
        )


def device_cells(body):
    return next(row for row in body["rows"] if row["device_id"] == DEVICE)["cells"]


@pytest.mark.asyncio
async def test_a_row_lands_in_the_hour_it_belongs_to(deployment):
    """Including the two that decide a boundary: the first millisecond of an hour
    and the last millisecond of the one before it."""
    server, sessions = deployment
    enrol(server, DAY)
    seed(
        server,
        [
            DAY + 3 * HOUR - 1,  # last ms of hour 2
            DAY + 3 * HOUR,  # first ms of hour 3
            DAY + 3 * HOUR + 1,
            DAY + 4 * HOUR - 1,  # last ms of hour 3
        ],
    )
    await build_rollup(sessions)

    cells = device_cells(await study_grid(sessions))

    assert cells[2]["records"] == 1
    assert cells[3]["records"] == 3
    assert cells[4]["records"] == 0


@pytest.mark.asyncio
async def test_every_hour_agrees_with_the_source_table(deployment):
    """The claim the whole view rests on, checked hour by hour rather than in
    total — a grid can hold the right sum with the rows in the wrong columns."""
    server, sessions = deployment
    enrol(server, DAY)
    # An uneven scatter, so few hours hold the same count and a shifted column
    # cannot pass by coincidence.
    seed(
        server,
        [
            DAY + hour * HOUR + minute * 60_000
            for hour in range(24)
            for minute in range(hour % 7 + 1)
        ],
    )
    await build_rollup(sessions)

    cells = device_cells(await study_grid(sessions))
    actual = {DAY + index * HOUR: cell["records"] for index, cell in enumerate(cells)}

    assert {hour: count for hour, count in actual.items() if count} == source_counts(
        server, DAY, DAY + 24 * HOUR
    )


@pytest.mark.asyncio
async def test_the_columns_partition_the_span(deployment):
    """No row counted twice, none lost between columns."""
    server, sessions = deployment
    enrol(server, DAY)
    seed(server, [DAY + index * 97_000 for index in range(900)])
    await build_rollup(sessions)

    cells = device_cells(await study_grid(sessions))

    assert sum(cell["records"] for cell in cells) == sum(
        source_counts(server, DAY, DAY + 24 * HOUR).values()
    )


@pytest.mark.asyncio
async def test_a_day_cell_equals_the_sum_of_its_hours(deployment):
    """The drill-down is otherwise showing a different quantity at each step."""
    server, sessions = deployment
    enrol(server, DAY)
    seed(server, [DAY + index * 137_000 for index in range(600)])
    await build_rollup(sessions)

    hours = device_cells(await study_grid(sessions, level="hour"))
    days = await study_grid(sessions, level="day")

    fifth = next(
        index for index, bucket in enumerate(days["buckets"]) if bucket["from"] == DAY
    )
    assert device_cells(days)[fifth]["records"] == sum(
        cell["records"] for cell in hours
    )


@pytest.mark.asyncio
async def test_a_display_timezone_recuts_the_same_rows(deployment):
    """Zurich's 5 March is not UTC's, so the totals differ — but every row inside
    the local day has to be accounted for exactly once."""
    server, sessions = deployment
    enrol(server, DAY - 48 * HOUR)
    seed(server, [DAY + index * 61_000 for index in range(2000)])
    await build_rollup(sessions)

    body = await study_grid(sessions, tz="Europe/Zurich")
    buckets = coverage_matrix.buckets_for("hour", DAY, ZoneInfo("Europe/Zurich"))

    assert body["timezone"] == "Europe/Zurich"
    assert body["buckets"][0]["from"] == buckets[0].start
    assert sum(cell["records"] for cell in device_cells(body)) == sum(
        source_counts(server, buckets[0].start, buckets[-1].end).values()
    )


@pytest.mark.asyncio
async def test_the_matrix_export_marks_the_hours_the_source_holds(deployment):
    """The reference spreadsheet encodes presence per device per hour, and this is
    the file that reproduces it."""
    server, sessions = deployment
    enrol(server, DAY)
    filled = [1, 4, 5, 9, 23]
    seed(server, [DAY + hour * HOUR + 5_000 for hour in filled])
    await build_rollup(sessions)

    android, ios = sessions
    async with android() as android_db, ios() as ios_db:
        response = await coverage_router.coverage_matrix_export(
            from_ts=DAY,
            to_ts=DAY + 24 * HOUR - 1,
            platform="android",
            tz="UTC",
            values=coverage_router.PRESENCE,
            android_db=android_db,
            ios_db=ios_db,
        )

    bundle = zipfile.ZipFile(io.BytesIO(response.body))
    rows = list(
        csv.reader(io.StringIO(bundle.read("android/battery.csv").decode("utf-8")))
    )
    (row,) = [entry for entry in rows[1:] if entry[0] == DEVICE]

    assert [index for index, value in enumerate(row[2:-1]) if value] == filled
    assert row[-1] == str(len(filled))
    assert row[1].endswith("01:00")


@pytest.mark.asyncio
async def test_a_bucket_outside_enrolment_reads_as_nothing_expected(deployment):
    """Against a real registry rather than a stubbed one, since this is what stops
    the grid reporting a study's first hours as a study-wide failure."""
    server, sessions = deployment
    enrol(server, DAY + 10 * HOUR)
    seed(server, [DAY + 11 * HOUR + 1_000])
    await build_rollup(sessions)

    cells = device_cells(await study_grid(sessions))

    assert cells[0]["state"] == coverage_matrix.NOT_EXPECTED
    assert cells[9]["state"] == coverage_matrix.NOT_EXPECTED
    assert cells[10]["state"] == coverage_matrix.MISSING
    assert cells[11]["records"] == 1
