"""The hourly rollup, against a real MySQL.

Bucketing, the upsert and the watermark are all things the database does, so a
stand-in session would only confirm the calls were made. These run against a
MySQL of their own: `pytest -m integration`.

What they establish is what every reader of the rollup depends on — rows land in
the hour they belong to, a second pass changes nothing, and a bucket that is
wrong for any reason is corrected by the next pass that touches its hour.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidCoverageHourly
from app.services import coverage_rollup

pytestmark = pytest.mark.integration

HOUR = coverage_rollup.HOUR_MS
DEVICE = "phone-a"
#: A round hour, so a test can add offsets without crossing a boundary by luck.
BASE_HOUR = 1_700_000_000_000 // HOUR * HOUR


@pytest_asyncio.fixture
async def session(clean_databases):
    engine = create_async_engine(clean_databases.url("aware_android"))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        await db.execute(text("DELETE FROM coverage_hourly"))
        await db.commit()
        yield db
    await engine.dispose()


def battery_rows(server, *timestamps, device=DEVICE):
    values = ", ".join(f"({ts}, '{device}', 1, 1, 1)" for ts in timestamps)
    server.run(
        "INSERT INTO battery (timestamp, device_id, battery_status, battery_level, "
        f"battery_scale) VALUES {values}",
        "aware_android",
    )


async def buckets(db, table="battery"):
    rows = (
        await db.execute(
            text(
                "SELECT device_id, hour_start, records, last_id FROM coverage_hourly "
                "WHERE table_name = :t ORDER BY hour_start"
            ),
            {"t": table},
        )
    ).all()
    return [(r.device_id, int(r.hour_start), int(r.records)) for r in rows]


@pytest.mark.asyncio
async def test_records_land_in_the_hour_they_arrived(session, clean_databases):
    battery_rows(clean_databases, BASE_HOUR, BASE_HOUR + 60_000, BASE_HOUR + HOUR + 5)

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [
        (DEVICE, BASE_HOUR, 2),
        (DEVICE, BASE_HOUR + HOUR, 1),
    ]


@pytest.mark.asyncio
async def test_a_second_pass_adds_nothing(session, clean_databases):
    """The property every count read from this table depends on."""
    battery_rows(clean_databases, BASE_HOUR, BASE_HOUR + 1)

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [(DEVICE, BASE_HOUR, 2)]


@pytest.mark.asyncio
async def test_rows_arriving_later_join_their_bucket(session, clean_databases):
    battery_rows(clean_databases, BASE_HOUR)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    battery_rows(clean_databases, BASE_HOUR + 10, BASE_HOUR + 20)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [(DEVICE, BASE_HOUR, 3)]


@pytest.mark.asyncio
async def test_the_watermark_does_not_go_backwards(session, clean_databases):
    """A late row for an earlier hour must not make old rows countable again."""
    battery_rows(clean_databases, BASE_HOUR + HOUR)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    battery_rows(clean_databases, BASE_HOUR)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [
        (DEVICE, BASE_HOUR, 1),
        (DEVICE, BASE_HOUR + HOUR, 1),
    ]


@pytest.mark.asyncio
async def test_devices_are_counted_apart(session, clean_databases):
    battery_rows(clean_databases, BASE_HOUR, device="phone-a")
    battery_rows(clean_databases, BASE_HOUR, BASE_HOUR + 1, device="phone-b")

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert sorted(await buckets(session)) == [
        ("phone-a", BASE_HOUR, 1),
        ("phone-b", BASE_HOUR, 2),
    ]


@pytest.mark.asyncio
async def test_a_sensor_split_over_two_tables_keeps_both(session, clean_databases):
    """`esm` and `wifi` are stored in two tables; the sensor-keyed cache skips
    them. Keyed by table, each is counted and the reader sums them."""
    battery_rows(clean_databases, BASE_HOUR)
    clean_databases.run(
        f"INSERT INTO screen (timestamp, device_id, screen_status) "
        f"VALUES ({BASE_HOUR}, '{DEVICE}', 1)",
        "aware_android",
    )

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session, "battery") == [(DEVICE, BASE_HOUR, 1)]
    assert await buckets(session, "screen") == [(DEVICE, BASE_HOUR, 1)]


@pytest.mark.asyncio
async def test_the_rollup_does_not_roll_itself_up(session, clean_databases):
    battery_rows(clean_databases, BASE_HOUR)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session, "coverage_hourly") == []
    assert await buckets(session, "record_counts") == []


@pytest.mark.asyncio
async def test_an_empty_database_produces_nothing(session):
    added = await coverage_rollup.refresh(
        session, AndroidCoverageHourly, "aware_android"
    )
    assert added == {}
    assert await buckets(session) == []


@pytest.mark.asyncio
async def test_reset_clears_the_watermark_with_the_rows(session, clean_databases):
    """Clearing the rollup has to make the next pass rebuild from zero."""
    battery_rows(clean_databases, BASE_HOUR, BASE_HOUR + 1)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    await coverage_rollup.reset(session, AndroidCoverageHourly)
    assert await buckets(session) == []

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")
    assert await buckets(session) == [(DEVICE, BASE_HOUR, 2)]


@pytest.mark.asyncio
async def test_a_wrong_bucket_corrects_itself(session, clean_databases):
    """The reason a bucket is recounted rather than added to.

    `_id` is auto-increment, so two inserts can commit out of order and leave a
    row below a watermark that has already moved past it — uncounted, and with an
    additive bucket, uncounted forever. Recounting fixes whatever the bucket says
    the next time its hour receives anything.
    """
    battery_rows(clean_databases, BASE_HOUR, BASE_HOUR + 1)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")
    assert await buckets(session) == [(DEVICE, BASE_HOUR, 2)]

    # However the count came to be wrong - a missed row, a bad write - the source
    # is what decides.
    await session.execute(
        text("UPDATE coverage_hourly SET records = 99 WHERE table_name = 'battery'")
    )
    await session.commit()

    battery_rows(clean_databases, BASE_HOUR + 2)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [(DEVICE, BASE_HOUR, 3)]


@pytest.mark.asyncio
async def test_a_table_with_nothing_new_is_left_alone(session, clean_databases):
    """A pass costs one indexed look per quiet table, not an aggregation."""
    battery_rows(clean_databases, BASE_HOUR)
    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    added = await coverage_rollup.refresh(
        session, AndroidCoverageHourly, "aware_android"
    )

    assert "battery" not in added
    assert await buckets(session) == [(DEVICE, BASE_HOUR, 1)]


@pytest.mark.asyncio
async def test_more_buckets_than_fit_in_one_statement(session, clean_databases, monkeypatch):
    """Buckets are written in chunks, so a backfill is not a round trip each."""
    monkeypatch.setattr(coverage_rollup, "WRITE_CHUNK", 2)
    battery_rows(
        clean_databases,
        BASE_HOUR,
        BASE_HOUR + HOUR,
        BASE_HOUR + 2 * HOUR,
        BASE_HOUR + 3 * HOUR,
        BASE_HOUR + 4 * HOUR,
    )

    await coverage_rollup.refresh(session, AndroidCoverageHourly, "aware_android")

    assert await buckets(session) == [
        (DEVICE, BASE_HOUR + n * HOUR, 1) for n in range(5)
    ]
