"""How fresh the cached counts are.

A refresher that has died leaves a dashboard indistinguishable from a study that
has gone quiet: the numbers simply stop moving, with nothing on screen to say
which it is. These cover the arithmetic that tells them apart.
"""

import time

import pytest

from app.routers import counts as counts_router


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Session:
    def __init__(self, stamped):
        self.stamped = stamped

    async def execute(self, _query):
        return _Result(self.stamped)

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_a_recent_refresh_is_not_stale():
    fresh = time.time() - 30
    status = await counts_router.counts_status(_Session(fresh), _Session(fresh))

    assert status["stale"] is False
    assert status["age_seconds"] == pytest.approx(30, abs=5)


@pytest.mark.asyncio
async def test_an_old_refresh_is_stale():
    old = time.time() - counts_router.STALE_AFTER_SECONDS - 60
    status = await counts_router.counts_status(_Session(old), _Session(old))

    assert status["stale"] is True


@pytest.mark.asyncio
async def test_a_cache_that_never_ran_is_stale():
    """No timestamp means no refresh has ever written, which is not 'fresh'."""
    status = await counts_router.counts_status(_Session(None), _Session(None))

    assert status["last_refreshed"] is None
    assert status["age_seconds"] is None
    assert status["stale"] is True


@pytest.mark.asyncio
async def test_a_platform_with_no_new_data_is_not_called_stale():
    """One pass writes both databases, writing only what changed.

    A platform receiving nothing leaves its `updated_at` where it was, so
    judging it on its own would report a healthy refresher as dead.
    """
    fresh, old = time.time() - 10, time.time() - 10_000
    status = await counts_router.counts_status(_Session(fresh), _Session(old))

    assert status["stale"] is False
    assert status["age_seconds"] == pytest.approx(10, abs=5)
    assert status["platforms"]["ios"]["age_seconds"] == pytest.approx(10_000, abs=5)
