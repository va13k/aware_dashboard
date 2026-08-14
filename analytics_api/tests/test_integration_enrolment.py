"""The enrolment rollup, against a real MySQL.

test_enrolment.py covers the derivation with stand-in rows, which confirms the
shape of the windows but never runs a statement. These build the table from
`db/init_all.sql`, write a study log and a rollup into it, and read back what the
service stored — so the column types, the rebuild and the researcher-owned
carve-out are answered by the database rather than by the test.

Slow enough to be opt-in: `pytest -m integration`.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidAwareStudy, AndroidCoverageHourly, AndroidDeviceEnrolment
from app.services import enrolment

pytestmark = pytest.mark.integration

DEVICE = "phone-a"
QUIET_DEVICE = "phone-b"
HOUR = 60 * 60 * 1000


@pytest_asyncio.fixture
async def android_session(clean_databases):
    engine = create_async_engine(clean_databases.url("aware_android"))
    yield (
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        clean_databases,
    )
    await engine.dispose()


def seed_study(server, rows):
    """`(device, timestamp, message, double_join, double_exit)` into aware_studies."""
    values = ",".join(
        f"('{device}',{timestamp},'{message}',{join},{exit_})"
        for device, timestamp, message, join, exit_ in rows
    )
    server.run(
        "INSERT INTO aware_studies "
        "(device_id, timestamp, study_compliance, double_join, double_exit) "
        f"VALUES {values}",
        "aware_android",
    )


def seed_coverage(server, rows):
    """`(device, hour_start)` into the rollup, standing in for arrived data."""
    values = ",".join(
        f"('accelerometer','{device}',{hour},10,1)" for device, hour in rows
    )
    server.run(
        "INSERT INTO coverage_hourly "
        "(table_name, device_id, hour_start, records, last_id) "
        f"VALUES {values}",
        "aware_android",
    )


def stored(server):
    """Every window the table holds, as `(device, joined, left, join_source)`."""
    raw = server.run(
        "SELECT device_id, joined_at, IFNULL(left_at, -1), join_source "
        "FROM device_enrolment ORDER BY device_id, joined_at",
        "aware_android",
    ).strip()
    if not raw:
        return []
    return [
        (parts[0], int(parts[1]), int(parts[2]), parts[3])
        for parts in (line.split("\t") for line in raw.splitlines())
    ]


async def run_refresh(sessionmaker_):
    async with sessionmaker_() as db:
        return await enrolment.refresh(
            db, AndroidDeviceEnrolment, AndroidCoverageHourly, AndroidAwareStudy
        )


@pytest.mark.asyncio
async def test_a_join_and_a_quit_land_as_one_closed_window(android_session):
    sessionmaker_, server = android_session
    seed_study(
        server,
        [
            (DEVICE, 1_000, "joined study", 0, 0),
            (DEVICE, 5_000, "quit study", 0, 0),
        ],
    )

    result = await run_refresh(sessionmaker_)

    assert stored(server) == [(DEVICE, 1_000, 5_000, enrolment.STUDY_EVENT)]
    assert result == {"devices": 1, "windows": 1, "researcher_owned": 0}


@pytest.mark.asyncio
async def test_a_rejoin_leaves_the_gap_between_two_windows(android_session):
    """The hours between quitting and coming back are hours nothing was
    expected, and only a second row can say so."""
    sessionmaker_, server = android_session
    seed_study(
        server,
        [
            (DEVICE, 1_000, "joined study", 0, 0),
            (DEVICE, 5_000, "quit study", 0, 0),
            (DEVICE, 9_000, "rejoined study", 0, 0),
        ],
    )

    await run_refresh(sessionmaker_)

    assert stored(server) == [
        (DEVICE, 1_000, 5_000, enrolment.STUDY_EVENT),
        (DEVICE, 9_000, -1, enrolment.STUDY_EVENT),
    ]


@pytest.mark.asyncio
async def test_a_device_with_only_data_is_backfilled_from_the_rollup(android_session):
    """The done-when for this step: every device with data has a join time."""
    sessionmaker_, server = android_session
    seed_coverage(server, [(QUIET_DEVICE, 4 * HOUR), (QUIET_DEVICE, 9 * HOUR)])

    await run_refresh(sessionmaker_)

    assert stored(server) == [(QUIET_DEVICE, 4 * HOUR, -1, enrolment.FIRST_DATA)]


@pytest.mark.asyncio
async def test_both_sources_are_covered_in_one_pass(android_session):
    sessionmaker_, server = android_session
    seed_study(server, [(DEVICE, 1_000, "joined study", 0, 0)])
    seed_coverage(server, [(DEVICE, 0), (QUIET_DEVICE, 4 * HOUR)])

    result = await run_refresh(sessionmaker_)

    assert stored(server) == [
        (DEVICE, 1_000, -1, enrolment.STUDY_EVENT),
        (QUIET_DEVICE, 4 * HOUR, -1, enrolment.FIRST_DATA),
    ]
    assert result["devices"] == 2


@pytest.mark.asyncio
async def test_a_second_pass_does_not_duplicate_the_windows(android_session):
    """The table is rebuilt rather than appended to, so a refresh every minute
    has to leave it holding exactly what one pass produces."""
    sessionmaker_, server = android_session
    seed_study(server, [(DEVICE, 1_000, "joined study", 0, 0)])

    await run_refresh(sessionmaker_)
    await run_refresh(sessionmaker_)

    assert stored(server) == [(DEVICE, 1_000, -1, enrolment.STUDY_EVENT)]


@pytest.mark.asyncio
async def test_a_later_quit_closes_a_window_an_earlier_pass_left_open(android_session):
    """A rebuild picks the withdrawal up without anything tracking what changed."""
    sessionmaker_, server = android_session
    seed_study(server, [(DEVICE, 1_000, "joined study", 0, 0)])
    await run_refresh(sessionmaker_)

    seed_study(server, [(DEVICE, 5_000, "quit study", 0, 0)])
    await run_refresh(sessionmaker_)

    assert stored(server) == [(DEVICE, 1_000, 5_000, enrolment.STUDY_EVENT)]


@pytest.mark.asyncio
async def test_a_researcher_owned_device_survives_the_rebuild(android_session):
    """Nothing writes `manual` yet. The carve-out is here from the start so the
    writer that lands later does not have to teach the rebuild to respect it."""
    sessionmaker_, server = android_session
    seed_study(server, [(DEVICE, 1_000, "joined study", 0, 0)])
    server.run(
        "INSERT INTO device_enrolment "
        "(device_id, joined_at, left_at, join_source, left_source) "
        f"VALUES ('{DEVICE}', 40, 90, 'manual', 'manual')",
        "aware_android",
    )

    result = await run_refresh(sessionmaker_)

    assert stored(server) == [(DEVICE, 40, 90, enrolment.MANUAL)]
    assert result["researcher_owned"] == 1


@pytest.mark.asyncio
async def test_the_window_follows_the_clients_own_account_of_the_moment(
    android_session,
):
    """A quit made with no signal reaches the server whenever the phone next
    connects; the window closes on the day the participant acted."""
    sessionmaker_, server = android_session
    seed_study(
        server,
        [
            (DEVICE, 1_000, "joined study", 0, 0),
            (DEVICE, 90_000, "quit study", 0, 5_000),
        ],
    )

    await run_refresh(sessionmaker_)

    assert stored(server) == [(DEVICE, 1_000, 5_000, enrolment.STUDY_EVENT)]


@pytest.mark.asyncio
async def test_an_empty_study_and_an_empty_rollup_leave_an_empty_table(android_session):
    sessionmaker_, server = android_session

    assert await run_refresh(sessionmaker_) == {
        "devices": 0,
        "windows": 0,
        "researcher_owned": 0,
    }
    assert stored(server) == []
