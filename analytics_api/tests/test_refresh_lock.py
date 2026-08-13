"""The refresh lock, against a real MySQL.

`GET_LOCK` is the database's behaviour, not the code's: it is held per connection
and released when that connection closes. A stand-in would only confirm the calls
were made, so these run against a MySQL of their own and are opt-in:
`pytest -m integration`.

What they establish is the property the counts depend on - two refreshers cannot
run at once, and a finished refresher leaves the lock free for the next one.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import AndroidRecordCount
from app.routers.counts import ANDROID_SOURCES
from app.services import record_counts

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def engine(clean_databases):
    engine = create_async_engine(clean_databases.url("aware_android"))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def other_engine(clean_databases):
    """A second engine, standing in for a second refresher process."""
    engine = create_async_engine(clean_databases.url("aware_android"))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_first_refresher_gets_the_lock(engine):
    async with record_counts.single_writer(engine) as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_a_second_refresher_is_turned_away(engine, other_engine):
    async with record_counts.single_writer(engine) as first:
        assert first is True
        async with record_counts.single_writer(other_engine) as second:
            assert second is False


@pytest.mark.asyncio
async def test_the_lock_is_free_once_the_first_refresher_finishes(engine, other_engine):
    async with record_counts.single_writer(engine) as first:
        assert first is True

    async with record_counts.single_writer(other_engine) as second:
        assert second is True


@pytest.mark.asyncio
async def test_the_lock_is_released_when_a_refresh_fails(engine, other_engine):
    with pytest.raises(RuntimeError):
        async with record_counts.single_writer(engine) as acquired:
            assert acquired is True
            raise RuntimeError("the refresh blew up")

    async with record_counts.single_writer(other_engine) as after:
        assert after is True


@pytest.mark.asyncio
async def test_different_names_do_not_block_each_other(engine, other_engine):
    async with record_counts.single_writer(engine, "one_refresh") as first:
        assert first is True
        async with record_counts.single_writer(other_engine, "another_refresh") as second:
            assert second is True


@pytest.mark.asyncio
async def test_two_refreshers_at_once_do_not_double_the_counts(
    clean_databases, engine, other_engine
):
    """The guarantee the lock exists for.

    Counts are folded in additively, so two refreshers reading the same watermark
    would each add the same rows. One holds the lock and works; the other is
    turned away and adds nothing.
    """
    device = "phone-a"
    rows = 5
    values = ", ".join(f"({i}, '{device}', 1, 1, 1)" for i in range(1, rows + 1))
    clean_databases.run(
        "INSERT INTO battery (timestamp, device_id, battery_status, battery_level, "
        f"battery_scale) VALUES {values}",
        "aware_android",
    )

    sources = {"battery": ANDROID_SOURCES["battery"]}

    async def refresher(refresher_engine):
        session_factory = async_sessionmaker(
            refresher_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with record_counts.single_writer(refresher_engine) as acquired:
            if not acquired:
                return "skipped"
            async with session_factory() as db:
                await record_counts.refresh(db, AndroidRecordCount, sources)
            return "refreshed"

    outcomes = await asyncio.gather(refresher(engine), refresher(other_engine))

    assert sorted(outcomes) == ["refreshed", "skipped"]
    counted = clean_databases.run(
        f"SELECT count FROM record_counts WHERE sensor = 'battery' "
        f"AND device_id = '{device}'",
        "aware_android",
    )
    assert int(counted.split()[-1]) == rows
