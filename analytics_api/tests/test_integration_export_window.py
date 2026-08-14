"""Ranged export paging, against a real MySQL.

The change under test swaps the paging key when a period is chosen: `_id` order
for a whole-table export, `(timestamp, _id)` for a windowed one. A stand-in
session cannot answer either of the questions that matters — whether the
database returns the rows in the order the cursor assumes, and whether rows
sharing a millisecond survive a batch boundary without being repeated or
skipped. Both are silent when wrong: the archive simply has the wrong rows in it.

Slow enough to be opt-in: `pytest -m integration`.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidAccelerometer, AndroidCoverageHourly
from app.routers import export as export_router
from app.services import coverage_rollup

pytestmark = pytest.mark.integration

DEVICE = "phone-a"
OTHER = "phone-b"
HOUR = coverage_rollup.HOUR_MS


@pytest_asyncio.fixture
async def android_session(clean_databases):
    engine = create_async_engine(clean_databases.url("aware_android"))
    yield (
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        clean_databases,
    )
    await engine.dispose()


def seed(server, rows, device=DEVICE):
    """`(timestamp, double_values_0)` pairs into accelerometer."""
    values = ",".join(f"({ts},'{device}',{x})" for ts, x in rows)
    server.run(
        "INSERT INTO accelerometer (timestamp, device_id, double_values_0) "
        f"VALUES {values}",
        "aware_android",
    )


async def exported(sessionmaker_, window, device_id=DEVICE):
    """Every timestamp `_paged` yields for this window, in order."""
    out = []
    async with sessionmaker_() as db:
        async for batch in export_router._paged(
            db, AndroidAccelerometer, device_id, lambda row: row.timestamp, window
        ):
            out.extend(batch)
    return out


@pytest.mark.asyncio
async def test_both_ends_of_the_window_are_inclusive(android_session):
    """A day chosen from its first to its last millisecond must contain both."""
    sessionmaker_, server = android_session
    seed(server, [(100, 1.0), (200, 2.0), (300, 3.0), (400, 4.0)])

    assert await exported(sessionmaker_, (200, 300)) == [200.0, 300.0]


@pytest.mark.asyncio
async def test_a_row_one_millisecond_outside_is_left_out(android_session):
    sessionmaker_, server = android_session
    seed(server, [(199, 1.0), (200, 2.0), (300, 3.0), (301, 4.0)])

    assert await exported(sessionmaker_, (200, 300)) == [200.0, 300.0]


@pytest.mark.asyncio
async def test_an_open_ended_window_runs_to_the_end_of_the_data(android_session):
    sessionmaker_, server = android_session
    seed(server, [(100, 1.0), (200, 2.0), (300, 3.0)])

    assert await exported(sessionmaker_, (200, None)) == [200.0, 300.0]
    assert await exported(sessionmaker_, (None, 200)) == [100.0, 200.0]


@pytest.mark.asyncio
async def test_the_window_comes_out_in_timestamp_order(android_session):
    """The cursor assumes the database returns rows in the order it pages by.
    Inserting out of order is what proves the ORDER BY is doing the work."""
    sessionmaker_, server = android_session
    seed(server, [(500, 1.0), (100, 2.0), (400, 3.0), (200, 4.0), (300, 5.0)])

    assert await exported(sessionmaker_, (100, 500)) == [100.0, 200.0, 300.0, 400.0, 500.0]


@pytest.mark.asyncio
async def test_rows_sharing_a_millisecond_survive_a_batch_boundary(
    android_session, monkeypatch
):
    """`_id` breaks ties in the cursor. Without it a batch ending inside a run of
    identical timestamps either repeats that run or skips past it, and at a
    hundred hertz identical timestamps are ordinary rather than exotic."""
    sessionmaker_, server = android_session
    monkeypatch.setattr(export_router, "EXPORT_BATCH", 3)
    seed(server, [(100, float(n)) for n in range(10)])

    produced = await exported(sessionmaker_, (100, 100))

    assert produced == [100.0] * 10


@pytest.mark.asyncio
async def test_paging_across_batches_neither_repeats_nor_skips(
    android_session, monkeypatch
):
    sessionmaker_, server = android_session
    monkeypatch.setattr(export_router, "EXPORT_BATCH", 4)
    seed(server, [(ts, float(ts)) for ts in range(1, 26)])

    assert await exported(sessionmaker_, (1, 25)) == [float(ts) for ts in range(1, 26)]


@pytest.mark.asyncio
async def test_the_window_does_not_cross_devices(android_session):
    sessionmaker_, server = android_session
    seed(server, [(100, 1.0), (200, 2.0)])
    seed(server, [(100, 9.0), (200, 9.0)], device=OTHER)

    assert await exported(sessionmaker_, (100, 200)) == [100.0, 200.0]


@pytest.mark.asyncio
async def test_no_window_still_walks_the_whole_table(android_session):
    """The unranged path is unchanged and must stay that way — it is what every
    existing export uses."""
    sessionmaker_, server = android_session
    seed(server, [(300, 1.0), (100, 2.0), (200, 3.0)])

    produced = await exported(sessionmaker_, export_router.ALL_TIME)

    assert sorted(produced) == [100.0, 200.0, 300.0]


@pytest.mark.asyncio
async def test_an_empty_window_yields_nothing(android_session):
    sessionmaker_, server = android_session
    seed(server, [(100, 1.0), (200, 2.0)])

    assert await exported(sessionmaker_, (500, 900)) == []


def seed_buckets(server, rows):
    """`(table, hour_start, records)` into the rollup."""
    values = ",".join(
        f"('{table}','{DEVICE}',{hour},{records},1)" for table, hour, records in rows
    )
    server.run(
        "INSERT INTO coverage_hourly "
        "(table_name, device_id, hour_start, records, last_id) "
        f"VALUES {values}",
        "aware_android",
    )


async def counted(sessionmaker_, window, tables=None):
    async with sessionmaker_() as db:
        return await coverage_rollup.records_in(
            db, AndroidCoverageHourly, window, tables
        )


@pytest.mark.asyncio
async def test_the_total_covers_the_hours_the_window_touches(android_session):
    """A bucket is a whole hour, so a window landing part-way through one counts
    that hour. The figure is hour-granular at its edges by construction."""
    sessionmaker_, server = android_session
    seed_buckets(
        server,
        [
            ("accelerometer", 0, 10),
            ("accelerometer", HOUR, 20),
            ("accelerometer", 2 * HOUR, 40),
        ],
    )

    assert await counted(sessionmaker_, (HOUR, 2 * HOUR - 1)) == 20
    assert await counted(sessionmaker_, (HOUR + 5, HOUR + 10)) == 20
    assert await counted(sessionmaker_, (0, 2 * HOUR)) == 70


@pytest.mark.asyncio
async def test_an_hour_ending_exactly_at_the_window_start_still_counts(android_session):
    """The bucket at `start - 1` covers up to `start`, so it overlaps. Getting
    this backwards drops a whole hour off the front of every total."""
    sessionmaker_, server = android_session
    seed_buckets(server, [("accelerometer", 0, 10), ("accelerometer", HOUR, 20)])

    assert await counted(sessionmaker_, (HOUR - 1, HOUR)) == 30


@pytest.mark.asyncio
async def test_a_total_can_be_restricted_to_one_sensors_tables(android_session):
    """A sensor stored across two tables is the sum of both, which is what the
    count cache cannot express."""
    sessionmaker_, server = android_session
    seed_buckets(
        server,
        [("accelerometer", 0, 10), ("esm", 0, 5), ("wifi", 0, 7)],
    )

    assert await counted(sessionmaker_, (0, HOUR), ["esm", "wifi"]) == 12
    assert await counted(sessionmaker_, (0, HOUR), ["accelerometer"]) == 10


@pytest.mark.asyncio
async def test_a_window_holding_nothing_totals_zero(android_session):
    sessionmaker_, server = android_session
    seed_buckets(server, [("accelerometer", 0, 10)])

    assert await counted(sessionmaker_, (50 * HOUR, 60 * HOUR)) == 0


@pytest.mark.asyncio
async def test_the_window_narrows_the_has_rows_guard(android_session):
    """An empty window is refused before the response begins, rather than
    producing an archive of header-only CSVs."""
    sessionmaker_, server = android_session
    seed(server, [(100, 1.0)])

    async with sessionmaker_() as db:
        assert await export_router._has_rows(db, AndroidAccelerometer, DEVICE, (50, 150))
        assert not await export_router._has_rows(
            db, AndroidAccelerometer, DEVICE, (500, 900)
        )
