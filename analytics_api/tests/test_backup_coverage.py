"""Period selection for the export: the windows offered and the dump they build.

The database side of coverage is two index seeks and an existence probe, so what
is worth pinning down here is the arithmetic around them — which windows get
offered, how a period turns into a mysqldump invocation, and how the progress
estimate is scaled to a slice of the span.
"""

import importlib

import pytest

from app.services import coverage

HOUR = coverage.HOUR_MS
DAY = coverage.DAY_MS
NEWEST = 1_754_000_000_000.0
NOW = 1_754_003_600_000.0


@pytest.fixture
def backup(monkeypatch):
    monkeypatch.setenv("MYSQL_ROOT_PASSWORD", "test-password")
    from app.routers import backup as module

    reloaded = importlib.reload(module)
    yield reloaded
    importlib.reload(module)


def window(offered, anchor, period):
    return next(
        entry for entry in offered if entry["anchor"] == anchor and entry["period"] == period
    )


def test_every_period_is_offered_against_both_anchors():
    offered = coverage.windows(NEWEST, NOW)
    assert len(offered) == len(coverage.PERIODS) * 2
    assert {entry["anchor"] for entry in offered} == {"data", "now"}


def test_a_data_anchored_window_ends_at_the_newest_row():
    offered = coverage.windows(NEWEST, NOW)
    hour = window(offered, "data", "hour")
    assert hour["to"] == NEWEST
    assert hour["from"] == NEWEST - HOUR


def test_a_clock_anchored_window_ends_now():
    offered = coverage.windows(NEWEST, NOW)
    day = window(offered, "now", "day")
    assert day["to"] == NOW
    assert day["from"] == NOW - DAY


def test_an_empty_database_offers_no_data_anchored_bounds():
    """With nothing stored there is no newest row to count back from, and a
    window with no bounds reads as unavailable."""
    offered = coverage.windows(None, NOW)
    hour = window(offered, "data", "hour")
    assert hour["from"] is None and hour["to"] is None
    assert hour["available"] is False
    assert window(offered, "now", "hour")["from"] == NOW - HOUR


def test_periods_are_offered_shortest_first():
    keys = [key for key, _, _ in coverage.PERIODS]
    assert keys == ["hour", "day", "week", "month", "year"]
    lengths = [length for _, _, length in coverage.PERIODS]
    assert lengths == sorted(lengths)


def test_a_whole_database_export_bounds_nothing(backup):
    command = backup._dump_command(None, None)
    assert command[-3:] == ["--databases", "aware_android", "aware_ios"]
    assert not any(argument.startswith("--where") for argument in command)


def test_a_period_export_bounds_every_table_on_timestamp(backup):
    command = backup._dump_command(1000.0, 2000.0)
    assert "--where=timestamp >= 1000 AND timestamp <= 2000" in command


@pytest.mark.parametrize("period", [(None, None), (1000.0, 2000.0)])
def test_no_export_carries_the_dashboard_caches(backup, period):
    """A cache summarises the `_id` values of the deployment that built it, so
    carrying one to another deployment restores watermarks for rows the target
    does not have. Every export leaves them behind, whole-database included."""
    command = backup._dump_command(*period)
    for database in ("aware_android", "aware_ios"):
        for table in ("record_counts", "coverage_hourly"):
            assert f"--ignore-table={database}.{table}" in command


def test_the_excluded_tables_are_the_ones_the_merge_skips(backup):
    """One list, so a cache added later is left out of both paths at once."""
    excluded = {
        argument.split(".", 1)[1]
        for argument in backup._dump_command(None, None)
        if argument.startswith("--ignore-table")
    }
    assert excluded == set(backup.dump_stream.CACHE_TABLES)


def test_the_where_clause_carries_no_exponent_notation(backup):
    """Timestamps are large doubles, and `1.754e+12` is not valid SQL."""
    command = backup._dump_command(1_754_000_000_000.0, 1_754_003_600_000.0)
    clause = next(argument for argument in command if argument.startswith("--where"))
    assert "e+" not in clause and "e-" not in clause
    assert "1754000000000" in clause and "1754003600000" in clause


@pytest.mark.asyncio
async def test_a_period_estimate_scales_to_its_share_of_the_span(backup, monkeypatch):
    async def span():
        return 0.0, 1000.0

    monkeypatch.setattr(backup, "_data_span", span)
    assert await backup._period_estimate(1000, 0.0, 500.0) == 500
    assert await backup._period_estimate(1000, 250.0, 750.0) == 500


@pytest.mark.asyncio
async def test_an_estimate_never_exceeds_the_whole_database(backup, monkeypatch):
    async def span():
        return 100.0, 200.0

    monkeypatch.setattr(backup, "_data_span", span)
    assert await backup._period_estimate(1000, 0.0, 10_000.0) == 1000


@pytest.mark.asyncio
async def test_a_period_outside_the_stored_span_estimates_nothing(backup, monkeypatch):
    async def span():
        return 100.0, 200.0

    monkeypatch.setattr(backup, "_data_span", span)
    assert await backup._period_estimate(1000, 500.0, 600.0) == 0


def test_a_period_export_is_named_for_the_days_it_covers(backup):
    # 1754000000000 ms is 2025-07-31T22:13:20Z.
    assert backup._stamp(1_754_000_000_000) == "20250731"
