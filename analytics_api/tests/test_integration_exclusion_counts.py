"""What the dashboard counts and what an export writes, against a real MySQL.

Exclusion takes effect in the export, which walks the devices it may write and
leaves the excluded ones out. The figures on screen came from two summary tables
that are keyed by device and were read across all of them, so the dashboard
reported rows the archive would never contain. With most of a study behind one
exclusion the gap is the majority of the number.

A stand-in session cannot settle this. The claim is that a `NOT IN` over the
count cache and a `NOT IN` over the hourly rollup select the same devices the
export's own `device_id` walk selects, and that is a statement about SQL over
the deployed schema rather than about which arguments a router passed.

Slow enough to be opt-in: `pytest -m integration`.
"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    AndroidAccelerometer,
    AndroidCoverageHourly,
    AndroidDeviceExclusion,
    AndroidRecordCount,
)
from app.routers import export as export_router
from app.services import coverage_rollup, exclusions, record_counts

pytestmark = pytest.mark.integration

KEPT = "phone-kept"
LEFT_OUT = "phone-left-out"
HOUR = coverage_rollup.HOUR_MS

#: Lopsided on purpose: the excluded phone holds most of the study, which is the
#: shape that makes a count read across every device obviously wrong.
KEPT_ROWS = 30
LEFT_OUT_ROWS = 300

ACCELEROMETER_TABLE = "accelerometer"


@pytest_asyncio.fixture
async def android(clean_databases):
    """A seeded Android database with one device excluded, and both caches warm."""
    server = clean_databases
    for device, count in ((KEPT, KEPT_ROWS), (LEFT_OUT, LEFT_OUT_ROWS)):
        values = ",".join(
            f"({HOUR + index},'{device}',{index})" for index in range(count)
        )
        server.run(
            "INSERT INTO accelerometer (timestamp, device_id, double_values_0) "
            f"VALUES {values}",
            "aware_android",
        )
    server.run(
        "INSERT INTO device_exclusions (device_id, excluded_at, note) "
        f"VALUES ('{LEFT_OUT}', 1, 'withdrew consent for analysis')",
        "aware_android",
    )

    engine = create_async_engine(server.url("aware_android"))
    sessionmaker_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker_() as db:
        await record_counts.refresh(
            db, AndroidRecordCount, {"accelerometer": AndroidAccelerometer}
        )
        await coverage_rollup.refresh(db, AndroidCoverageHourly, "aware_android")
    yield sessionmaker_
    await engine.dispose()


async def exported_row_count(db) -> int:
    """The rows an export would actually write for the accelerometer.

    Counted the way the export selects them — over the devices it is willing to
    walk — so this is the archive's own figure rather than a restatement of the
    filter under test.
    """
    device_ids = await export_router._device_ids_for_model(db, AndroidAccelerometer)
    total = 0
    for device_id in device_ids:
        counted = await db.execute(
            select(func.count())
            .select_from(AndroidAccelerometer)
            .where(AndroidAccelerometer.device_id == device_id)
        )
        total += int(counted.scalar() or 0)
    return total


class TestTheExportIsTheFigureOnScreen:
    @pytest.mark.asyncio
    async def test_the_export_writes_only_the_device_it_kept(self, android):
        """The premise: without this the rest measures nothing."""
        async with android() as db:
            assert await exported_row_count(db) == KEPT_ROWS

    @pytest.mark.asyncio
    async def test_the_count_cache_total_matches_what_the_export_writes(self, android):
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)
            totals = await record_counts.sensor_totals(
                db, AndroidRecordCount, exclude=left_out
            )

            records, devices = totals["accelerometer"]
            assert records == await exported_row_count(db)
            assert records == KEPT_ROWS
            assert devices == 1

    @pytest.mark.asyncio
    async def test_the_rollup_total_matches_what_the_export_writes(self, android):
        """The windowed figure, which is what an export dialog shows."""
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)
            counted = await coverage_rollup.records_in(
                db,
                AndroidCoverageHourly,
                (None, None),
                [ACCELEROMETER_TABLE],
                exclude=left_out,
            )

            assert counted == await exported_row_count(db)
            assert counted == KEPT_ROWS

    @pytest.mark.asyncio
    async def test_counting_every_device_is_the_figure_that_was_wrong(self, android):
        """Asked without the exclusion set both caches report the whole study, so
        these tests fail on a reverted filter rather than on a changed fixture."""
        async with android() as db:
            totals = await record_counts.sensor_totals(db, AndroidRecordCount)
            counted = await coverage_rollup.records_in(
                db, AndroidCoverageHourly, (None, None), [ACCELEROMETER_TABLE]
            )

            assert totals["accelerometer"][0] == KEPT_ROWS + LEFT_OUT_ROWS
            assert counted == KEPT_ROWS + LEFT_OUT_ROWS


class TestWhatTheExclusionHoldsBack:
    @pytest.mark.asyncio
    async def test_the_cache_accounts_for_the_excluded_rows(self, android):
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)
            held_back = await record_counts.sensor_totals_within(
                db, AndroidRecordCount, left_out
            )

            assert held_back["accelerometer"] == (LEFT_OUT_ROWS, 1)

    @pytest.mark.asyncio
    async def test_the_two_figures_add_up_to_what_arrived(self, android):
        """The pair is what makes the smaller number legible: a researcher can see
        the download and the reason it is not the whole study."""
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)
            analysis = await coverage_rollup.records_in(
                db, AndroidCoverageHourly, (None, None), exclude=left_out
            )
            held_back = await coverage_rollup.records_in(
                db, AndroidCoverageHourly, (None, None), only=left_out
            )

            assert analysis + held_back == KEPT_ROWS + LEFT_OUT_ROWS

    @pytest.mark.asyncio
    async def test_the_excluded_devices_are_counted_over_the_same_window(self, android):
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)

            assert (
                await coverage_rollup.devices_with_records(
                    db, AndroidCoverageHourly, (None, None), only=left_out
                )
                == 1
            )

    @pytest.mark.asyncio
    async def test_a_window_the_excluded_phone_is_silent_in_holds_nothing_back(
        self, android
    ):
        """A device excluded from the study but absent from the chosen period
        takes nothing out of it, so the pair stays honest per window."""
        async with android() as db:
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)
            empty = (10 * HOUR, 11 * HOUR)

            assert (
                await coverage_rollup.records_in(
                    db, AndroidCoverageHourly, empty, only=left_out
                )
                == 0
            )
            assert (
                await coverage_rollup.devices_with_records(
                    db, AndroidCoverageHourly, empty, only=left_out
                )
                == 0
            )


class TestNothingExcluded:
    @pytest.mark.asyncio
    async def test_a_study_with_no_exclusions_counts_every_device(self, android):
        """Including the device back in restores the whole study to both figures,
        so an exclusion is a state rather than a one-way door."""
        async with android() as db:
            await exclusions.include(db, AndroidDeviceExclusion, LEFT_OUT)
            left_out = await exclusions.excluded_ids(db, AndroidDeviceExclusion)

            assert left_out == set()
            totals = await record_counts.sensor_totals(
                db, AndroidRecordCount, exclude=left_out
            )
            assert totals["accelerometer"][0] == KEPT_ROWS + LEFT_OUT_ROWS
            assert await exported_row_count(db) == KEPT_ROWS + LEFT_OUT_ROWS

    @pytest.mark.asyncio
    async def test_nothing_is_held_back_when_nothing_is_excluded(self, android):
        async with android() as db:
            assert (
                await record_counts.sensor_totals_within(db, AndroidRecordCount, set())
                == {}
            )
            assert (
                await coverage_rollup.records_in(
                    db, AndroidCoverageHourly, (None, None), only=set()
                )
                == 0
            )
