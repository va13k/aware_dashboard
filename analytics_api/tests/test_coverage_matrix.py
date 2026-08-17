"""The grid's columns, and what a cell says.

Two things here are easy to get wrong and invisible once wrong. Buckets are cut in
the display timezone, so a column's width follows the calendar — 28 to 31 days in
a month, 23 to 25 hours in a day across a daylight-saving change — and a
fixed-width bucket drifts, putting every later column's data in its neighbour. And
a bucket only partly inside an enrolment window expects only its covered part,
which is what lets the hour a participant joined read as the partial hour it was.

The rest establishes what a cell claims: an event sensor's busy hour reads as
`present`, and `reporting as configured` is reserved for a bucket judged against a
rate the config actually carries.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import coverage_matrix, sensor_rates

HOUR = coverage_matrix.HOUR_MS
UTC = ZoneInfo("UTC")


def at(year, month, day, hour=0, zone=UTC) -> int:
    return int(datetime(year, month, day, hour, tzinfo=zone).timestamp() * 1000)


def test_month_level_draws_the_anchors_year_as_twelve_columns():
    buckets = coverage_matrix.buckets_for("month", at(2026, 8, 17), UTC)

    assert len(buckets) == 12
    assert buckets[0].key == "2026-01"
    assert buckets[0].start == at(2026, 1, 1)
    assert buckets[-1].end == at(2027, 1, 1)
    assert [bucket.label for bucket in buckets[:3]] == ["Jan", "Feb", "Mar"]


def test_month_columns_are_the_real_lengths_of_their_months():
    """A fixed 30-day bucket would put March's data in February's column."""
    buckets = coverage_matrix.buckets_for("month", at(2026, 1, 1), UTC)

    assert buckets[0].hours == 31 * 24  # January
    assert buckets[1].hours == 28 * 24  # February 2026
    assert buckets[3].hours == 30 * 24  # April


def test_february_gains_a_day_in_a_leap_year():
    buckets = coverage_matrix.buckets_for("month", at(2024, 6, 1), UTC)

    assert buckets[1].hours == 29 * 24


def test_day_level_draws_the_anchors_month():
    buckets = coverage_matrix.buckets_for("day", at(2026, 2, 17), UTC)

    assert len(buckets) == 28
    assert buckets[0].key == "2026-02-01"
    assert buckets[-1].end == at(2026, 3, 1)


def test_hour_level_draws_the_anchors_day():
    buckets = coverage_matrix.buckets_for("hour", at(2026, 8, 17, 13), UTC)

    assert len(buckets) == 24
    assert buckets[0].start == at(2026, 8, 17)
    assert buckets[13].label == "13"
    assert all(bucket.hours == 1 for bucket in buckets)


def test_columns_partition_the_span_without_gaps_or_overlap():
    """Every level, since a bucket carries the hours between its own edges and a
    seam would count an hour twice or lose it."""
    for level, anchor in (
        ("month", at(2026, 3, 9)),
        ("day", at(2026, 3, 9)),
        ("hour", at(2026, 3, 9, 5)),
    ):
        buckets = coverage_matrix.buckets_for(level, anchor, UTC)
        for earlier, later in zip(buckets, buckets[1:]):
            assert earlier.end == later.start, level


def test_buckets_are_cut_in_the_display_timezone():
    """A local day does not start when a UTC day does, and a grid labelled in
    local hours has to hold the hours the participant lived."""
    zone = ZoneInfo("Europe/Zurich")
    buckets = coverage_matrix.buckets_for("hour", at(2026, 8, 17, 13), zone)

    # Zurich is UTC+2 in August, so its midnight is 22:00 the previous day UTC.
    assert buckets[0].start == at(2026, 8, 16, 22)
    assert len(buckets) == 24


def test_a_spring_forward_day_has_twenty_three_columns():
    """The hour that does not exist locally is not a column."""
    zone = ZoneInfo("Europe/Zurich")
    buckets = coverage_matrix.buckets_for("hour", at(2026, 3, 29, 12, zone), zone)

    assert len(buckets) == 23
    assert sum(bucket.hours for bucket in buckets) == 23


def test_an_autumn_day_covers_twenty_five_hours():
    zone = ZoneInfo("Europe/Zurich")
    buckets = coverage_matrix.buckets_for("hour", at(2026, 10, 25, 12, zone), zone)

    assert sum(bucket.hours for bucket in buckets) == 25


def test_an_unknown_timezone_falls_back_to_utc():
    """The name comes from a browser control, and a readable grid in UTC beats an
    error page."""
    assert str(coverage_matrix.resolve_timezone("Mars/Olympus")) == "UTC"
    assert str(coverage_matrix.resolve_timezone(None)) == "UTC"
    assert str(coverage_matrix.resolve_timezone("Europe/Zurich")) == "Europe/Zurich"


def test_an_unknown_level_is_refused():
    try:
        coverage_matrix.buckets_for("fortnight", at(2026, 8, 17), UTC)
    except ValueError as error:
        assert "fortnight" in str(error)
    else:
        raise AssertionError("an unknown level should not build buckets")


NOW = at(2026, 8, 20)


def one_hour(hour: int) -> coverage_matrix.Bucket:
    return coverage_matrix.Bucket(
        key="b", label="b", start=at(2026, 8, 17, hour), end=at(2026, 8, 17, hour + 1)
    )


def test_a_bucket_before_enrolment_is_covered_for_no_time():
    bucket = one_hour(3)
    windows = [{"joined_at": at(2026, 8, 17, 10), "left_at": None}]

    assert coverage_matrix.covered_hours(bucket, windows, NOW) == 0


def test_a_bucket_inside_enrolment_is_fully_covered():
    windows = [{"joined_at": at(2026, 8, 17, 10), "left_at": None}]

    assert coverage_matrix.covered_hours(one_hour(11), windows, NOW) == 1


def test_the_joining_hour_is_covered_only_in_part():
    """Which is what stops the grid crying wolf on its left edge."""
    joined = at(2026, 8, 17, 10) + 30 * 60 * 1000
    windows = [{"joined_at": joined, "left_at": None}]

    assert coverage_matrix.covered_hours(one_hour(10), windows, NOW) == 0.5


def test_a_gap_between_two_windows_expects_nothing():
    """The reason windows are stored one per join: a single span would report
    every hour a participant had quit as missing data."""
    windows = [
        {"joined_at": at(2026, 8, 17, 1), "left_at": at(2026, 8, 17, 4)},
        {"joined_at": at(2026, 8, 17, 8), "left_at": None},
    ]

    assert coverage_matrix.covered_hours(one_hour(2), windows, NOW) == 1
    assert coverage_matrix.covered_hours(one_hour(6), windows, NOW) == 0
    assert coverage_matrix.covered_hours(one_hour(9), windows, NOW) == 1


def test_an_open_window_is_covered_up_to_now():
    windows = [{"joined_at": at(2026, 8, 17), "left_at": None}]
    bucket = coverage_matrix.Bucket(
        key="b", label="b", start=at(2026, 8, 19, 23), end=at(2026, 8, 20, 1)
    )

    assert coverage_matrix.covered_hours(bucket, windows, NOW) == 1


def test_a_device_with_no_windows_expects_nothing():
    assert coverage_matrix.covered_hours(one_hour(5), None, NOW) == 0
    assert coverage_matrix.covered_hours(one_hour(5), [], NOW) == 0


def rate(per_hour, basis=sensor_rates.SAMPLED):
    return sensor_rates.ExpectedRate(
        sensor_key="s", basis=basis, per_hour=per_hour, interval_seconds=1
    )


def test_a_bucket_meeting_its_expectation_reports_as_configured():
    cell = coverage_matrix.cell(60, one_hour(4), 1.0, rate(60))

    assert cell["state"] == coverage_matrix.REPORTING
    assert cell["expected"] == 60
    assert cell["records"] == 60


def test_a_bucket_materially_short_of_its_expectation_reads_as_under():
    cell = coverage_matrix.cell(6, one_hour(4), 1.0, rate(60))

    assert cell["state"] == coverage_matrix.UNDER
    assert cell["expected"] == 60


def test_the_expectation_scales_with_the_covered_part_of_a_bucket():
    """Half an hour of enrolment expects half the records, so a participant who
    joined at half past does not read as under-reporting for it."""
    cell = coverage_matrix.cell(30, one_hour(4), 0.5, rate(60))

    assert cell["expected"] == 30
    assert cell["state"] == coverage_matrix.REPORTING


def test_an_expected_bucket_with_nothing_in_it_is_missing():
    cell = coverage_matrix.cell(0, one_hour(4), 1.0, rate(60))

    assert cell["state"] == coverage_matrix.MISSING


def test_an_uncovered_bucket_expects_nothing_whatever_the_rate():
    cell = coverage_matrix.cell(0, one_hour(4), 0.0, rate(60))

    assert cell["state"] == coverage_matrix.NOT_EXPECTED
    assert "expected" not in cell


def test_an_event_sensors_busy_hour_is_present_rather_than_reporting():
    """`reporting as configured` would assert a comparison against a rate that
    does not exist."""
    cell = coverage_matrix.cell(
        12, one_hour(4), 1.0, sensor_rates.ExpectedRate("calls", sensor_rates.EVENT)
    )

    assert cell["state"] == coverage_matrix.PRESENT
    assert cell["expected"] is None


def test_an_event_sensors_empty_hour_is_missing_not_under():
    cell = coverage_matrix.cell(
        0, one_hour(4), 1.0, sensor_rates.ExpectedRate("calls", sensor_rates.EVENT)
    )

    assert cell["state"] == coverage_matrix.MISSING


def test_a_scan_sensors_cell_says_its_figure_is_a_floor():
    cell = coverage_matrix.cell(500, one_hour(4), 1.0, rate(60, sensor_rates.SCANNED))

    assert cell["floor"] is True
    assert cell["basis"] == sensor_rates.SCANNED


def test_the_aggregate_cell_counts_required_sensors_that_reported():
    cell = coverage_matrix.aggregate_cell(
        {"battery": 4, "screen": 0}, ["battery", "screen", "calls"], one_hour(4), 1.0
    )

    assert (cell["reporting"], cell["required"]) == (1, 3)
    assert cell["fraction"] == round(1 / 3, 4)


def test_the_aggregate_cell_ignores_sensors_the_study_did_not_ask_for():
    """A sensor still uploading after being switched off must not push the
    fraction of what was asked for above what was asked for."""
    cell = coverage_matrix.aggregate_cell(
        {"battery": 4, "magnetometer": 900}, ["battery"], one_hour(4), 1.0
    )

    assert (cell["reporting"], cell["required"]) == (1, 1)
    assert cell["fraction"] == 1.0


def test_an_uncovered_aggregate_cell_expects_nothing():
    cell = coverage_matrix.aggregate_cell({}, ["battery"], one_hour(4), 0.0)

    assert cell["state"] == coverage_matrix.NOT_EXPECTED
