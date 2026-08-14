"""Bounding an export to a period.

Two things decide whether this is right: which rows come out, and what the
progress bar is measured against. Both ends of a window are inclusive, so the
boundary rows are the ones worth pinning down — an export that silently drops
the last millisecond of a chosen day is indistinguishable from one that works.

The paging change underneath is covered against a real MySQL in
test_integration_export_window.py, because ordering and index use are exactly
what a stand-in session cannot answer.
"""

import pytest

from app.routers import export as export_router


class _Model:
    """Stands in for a data table, with the columns the window touches."""

    __tablename__ = "accelerometer"


def test_no_period_given_reads_as_the_whole_table():
    assert export_router._window(None, None) is export_router.ALL_TIME


@pytest.mark.parametrize(
    "given, expected",
    [
        ((1_000.0, 2_000.0), (1_000.0, 2_000.0)),
        ((None, 2_000.0), (None, 2_000.0)),
        ((1_000.0, None), (1_000.0, None)),
    ],
)
def test_one_or_both_ends_are_kept_as_given(given, expected):
    assert export_router._window(*given) == expected


def test_a_reversed_pair_is_read_as_the_period_it_means():
    """The two ends are a range, not an order, so swapping them is not an error
    the researcher should have to go back and correct."""
    assert export_router._window(9_000.0, 1_000.0) == (1_000.0, 9_000.0)


def test_a_windowed_export_is_not_all_time():
    """`ALL_TIME` selects the `_id` paging path, so anything that compares equal
    to it silently exports the whole table."""
    assert export_router._window(0.0, 0.0) != export_router.ALL_TIME


def test_a_sensor_spread_over_two_tables_still_resolves():
    """`esm` and `wifi` are absent from the count cache's source map because
    they live in two tables each. Counting them is why the rollup is keyed by
    table, so the export must reach them through the export models."""
    tables = export_router._sensor_tables("ios", "esm")

    assert len(tables) >= 1
    assert all(isinstance(name, str) and name for name in tables)


def test_an_unknown_sensor_names_no_tables():
    assert export_router._sensor_tables("android", "not_a_sensor") == []


def test_every_android_sensor_names_the_table_it_reads():
    """A sensor whose tables cannot be named would count as zero in a windowed
    export while still writing rows, so the bar would sit at nothing."""
    for sensor in export_router.ANDROID_EXPORT_MODELS:
        assert export_router._sensor_tables("android", sensor), sensor
