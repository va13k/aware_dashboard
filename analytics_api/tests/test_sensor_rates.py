"""The expected rate a bucket is judged against.

The failure this guards is silent and large: the same setting name carries
different units on the two clients, so reading Android's `frequency_processor`
of 60 as microseconds — or iOS's 60000000 as seconds — is wrong by a factor of a
million and produces a grid that is uniformly red or uniformly green while
looking entirely plausible.

The rest is about what the model refuses to claim. A sensor the phone writes on
an event has no rate to expect, a setting the config does not carry cannot be
guessed at, a scan sensor's interval bounds its scans rather than its rows, and a
sensor the client filters — by a threshold, or by only writing while the phone
moves — has an interval that bounds its rows from above. Each of those has to stay
distinguishable from "reporting as configured", because a cell that asserts a
comparison nobody made is worse than one that admits there is nothing to compare.
"""

from app.services import sensor_rates


def test_android_hardware_rates_read_as_microseconds():
    """50 Hz is 180,000 records an hour, not 180,000,000,000."""
    rate = sensor_rates.expected_for(
        "android", "accelerometer", {"frequency_accelerometer": 20000}
    )

    assert rate.interval_seconds == 0.02
    assert rate.per_hour == 180_000
    assert rate.basis == sensor_rates.SAMPLED
    assert rate.comparable


def test_android_polling_rates_read_as_seconds():
    rate = sensor_rates.expected_for(
        "android", "processor", {"frequency_processor": 60}
    )

    assert rate.interval_seconds == 60
    assert rate.per_hour == 60


def test_ios_processor_reads_as_microseconds_where_android_reads_seconds():
    """The one that makes the unit per platform rather than per setting name: both
    configs mean once a minute, and they spell it a million apart."""
    android = sensor_rates.expected_for(
        "android", "processor", {"frequency_processor": 60}
    )
    ios = sensor_rates.expected_for(
        "ios", "processor", {"frequency_processor": 60_000_000}
    )

    assert android.per_hour == ios.per_hour == 60


def test_plugin_rates_read_as_minutes():
    rate = sensor_rates.expected_for(
        "android", "plugin-ambient-noise", {"frequency_plugin_ambient_noise": 15}
    )

    assert rate.interval_seconds == 900
    assert rate.per_hour == 4


def test_an_event_sensor_expects_nothing():
    """No configuration predicts how often someone takes a call."""
    rate = sensor_rates.expected_for("android", "calls", {"status_calls": True})

    assert rate.basis == sensor_rates.EVENT
    assert rate.per_hour is None
    assert not rate.comparable


def test_a_missing_setting_is_unconfigured_rather_than_defaulted():
    """Distinguishable from an event sensor: one is how the sensor works, the
    other is something absent from the config."""
    rate = sensor_rates.expected_for("android", "accelerometer", {})

    assert rate.basis == sensor_rates.UNCONFIGURED
    assert rate.setting == "frequency_accelerometer"
    assert not rate.comparable


def test_an_unusable_interval_expects_nothing():
    """Zero means off or as-fast-as-possible depending on the sensor, and neither
    is a number a bucket can be judged against."""
    for value in (0, -1, "", "sometimes", None, True):
        rate = sensor_rates.expected_for(
            "android", "accelerometer", {"frequency_accelerometer": value}
        )
        assert not rate.comparable, value


def test_string_values_are_accepted():
    """The micro-server config serialises every value as a string."""
    rate = sensor_rates.expected_for(
        "ios", "bluetooth", {"frequency_bluetooth": "60"}
    )

    assert rate.per_hour == 60


def test_a_scan_sensor_reports_its_figure_as_a_floor():
    """Bluetooth writes a row per device in range, so 60 scans an hour is a lower
    bound on rows and a count above it proves nothing about the scan."""
    rate = sensor_rates.expected_for(
        "android", "bluetooth", {"frequency_bluetooth": 60}
    )

    assert rate.basis == sensor_rates.SCANNED
    assert rate.is_floor
    assert rate.per_hour == 60


def test_a_threshold_makes_the_configured_rate_a_ceiling():
    """The client discards a reading within the threshold of the one before it, so
    the interval bounds the rows rather than predicting them — a phone left on a
    desk writes almost none of the 180,000 an hour it is sampling at."""
    rate = sensor_rates.expected_for(
        "android",
        "accelerometer",
        {"frequency_accelerometer": 20000, "threshold_accelerometer": 0.1},
    )

    assert rate.basis == sensor_rates.GATED
    assert rate.is_ceiling
    assert rate.per_hour == 180_000
    assert rate.gated_by == ("threshold_accelerometer",)
    assert not rate.comparable


def test_a_zero_threshold_leaves_the_rate_comparable():
    """Every config carries the setting; only a positive one filters anything."""
    rate = sensor_rates.expected_for(
        "android",
        "accelerometer",
        {"frequency_accelerometer": 20000, "threshold_accelerometer": 0},
    )

    assert rate.basis == sensor_rates.SAMPLED
    assert rate.comparable


def test_significant_motion_gates_the_sensors_it_stops_and_no_others():
    """With it on, the five motion sensors write nothing while the phone is still,
    so an hour of stillness is an empty bucket rather than a shortfall. Light is
    not one of them and stays judged by its rate."""
    settings = {
        "status_significant_motion": True,
        "frequency_accelerometer": 20000,
        "frequency_light": 20000,
    }

    gated = sensor_rates.expected_for("android", "accelerometer", settings)
    ungated = sensor_rates.expected_for("android", "light", settings)

    assert gated.gated_by == ("status_significant_motion",)
    assert not gated.comparable
    assert ungated.basis == sensor_rates.SAMPLED
    assert ungated.comparable


def test_significant_motion_does_not_gate_ios():
    """iOS carries it as a sensor of its own and nothing there returns early on
    it, so an iPhone's accelerometer stays judged against its rate."""
    rate = sensor_rates.expected_for(
        "ios",
        "accelerometer",
        {"status_significant_motion": True, "frequency_accelerometer": 20000},
    )

    assert rate.basis == sensor_rates.SAMPLED
    assert rate.comparable


def test_both_gates_are_named_together():
    """The name is what a researcher changes, so a row filtered two ways has to
    say both rather than the first one found."""
    rate = sensor_rates.expected_for(
        "android",
        "gyroscope",
        {
            "frequency_gyroscope": 20000,
            "threshold_gyroscope": 0.5,
            "status_significant_motion": "true",
        },
    )

    assert rate.gated_by == ("threshold_gyroscope", "status_significant_motion")


def test_every_motion_gated_sensor_is_a_stream_the_rate_table_knows():
    """A key misspelt in the set would gate nothing, silently and forever."""
    assert sensor_rates.MOTION_GATED <= set(sensor_rates.ANDROID_RATES)


def test_the_fastest_provider_sets_a_shared_table_rate():
    """Three location providers write to one table; the quickest of them is what
    the table already receives."""
    rate = sensor_rates.expected_for(
        "android",
        "locations",
        {"frequency_location_gps": 300, "frequency_location_network": 30},
    )

    assert rate.interval_seconds == 30
    assert rate.setting == "frequency_location_network"


def test_an_unusable_provider_does_not_hide_a_usable_one():
    rate = sensor_rates.expected_for(
        "android",
        "locations",
        {"frequency_location_gps": 0, "frequency_location_network": 30},
    )

    assert rate.interval_seconds == 30


def test_every_platform_table_resolves_against_the_deployed_configs():
    """A table entry naming a setting no config carries would silently mark that
    sensor unconfigured forever, which no test of a single sensor would catch."""
    for platform in (sensor_rates.ANDROID, sensor_rates.IOS):
        rates = sensor_rates.rates_for(platform, {})
        assert set(rates) == set(sensor_rates.RATES[platform])
        assert all(entry.basis == sensor_rates.UNCONFIGURED for entry in rates.values())


def test_an_unknown_platform_is_refused():
    try:
        sensor_rates.expected_for("symbian", "accelerometer", {})
    except ValueError as error:
        assert "symbian" in str(error)
    else:
        raise AssertionError("an unknown platform should not resolve")
