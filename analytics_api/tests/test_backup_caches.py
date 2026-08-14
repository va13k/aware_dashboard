"""What an import leaves the dashboard's caches holding.

Neither cache travels in a dump, so after an import both describe a database
that has changed underneath them. Getting this wrong is quiet and permanent: a
watermark left above the restored `_id` values makes the incremental refresh see
nothing new, and the imported data never reaches the dashboard at all.

The refreshes themselves are covered by test_record_counts.py and
test_coverage_rollup.py. What matters here is which of them an import calls, and
in which order.
"""

import asyncio
import importlib

import pytest

from app.services import dump_stream


@pytest.fixture
def backup(monkeypatch):
    monkeypatch.setenv("MYSQL_ROOT_PASSWORD", "test-password")
    from app.routers import backup as module

    reloaded = importlib.reload(module)
    yield reloaded
    importlib.reload(module)


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


@pytest.fixture
def calls(backup, monkeypatch):
    """Records `(cache, action, database)` in the order the import performs it."""
    performed: list[tuple[str, str, str]] = []

    def record(cache, action):
        async def called(_db, model, argument=None):
            database = "aware_ios" if "Ios" in model.__name__ else "aware_android"
            performed.append((cache, action, database))

        return called

    for module, cache in ((backup.record_counts, "counts"), (backup.coverage_rollup, "coverage")):
        for action in ("reset", "refresh"):
            monkeypatch.setattr(module, action, record(cache, action))

    monkeypatch.setattr(backup, "AndroidSessionLocal", _Session)
    monkeypatch.setattr(backup, "IosSessionLocal", _Session)
    return performed


def test_a_replace_clears_both_caches_before_rebuilding(backup, calls):
    """A restore drops and refills the tables both caches summarise, so every
    tally and watermark they hold describes rows that no longer exist."""
    asyncio.run(backup._refresh_counts(dump_stream.REPLACE))

    for database in ("aware_android", "aware_ios"):
        for cache in ("counts", "coverage"):
            performed = [entry for entry in calls if entry[0] == cache and entry[2] == database]
            assert performed == [(cache, "reset", database), (cache, "refresh", database)]


def test_a_merge_rebuilds_both_caches_without_clearing_them(backup, calls):
    """Merged rows take fresh `_id` values above every watermark, so what is
    already counted stays counted and the incremental pass folds the rest in."""
    asyncio.run(backup._refresh_counts(dump_stream.MERGE))

    assert not [entry for entry in calls if entry[1] == "reset"]
    assert {(cache, database) for cache, _, database in calls} == {
        ("counts", "aware_android"),
        ("counts", "aware_ios"),
        ("coverage", "aware_android"),
        ("coverage", "aware_ios"),
    }


@pytest.mark.parametrize("mode", [dump_stream.REPLACE, dump_stream.MERGE])
def test_the_coverage_rollup_is_not_left_to_the_next_scheduled_pass(backup, calls, mode):
    """The import reports done and a study manager reads the page immediately.
    A rollup refreshed only on the scheduler's next pass is stale for as long as
    the interval, while the counts beside it are current."""
    asyncio.run(backup._refresh_counts(mode))

    assert ("coverage", "refresh", "aware_android") in calls
    assert ("coverage", "refresh", "aware_ios") in calls
