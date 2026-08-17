"""How many records an hour of a sensor should hold, per the study config.

The rollup says how many records a bucket holds; on its own that is a number with
nothing to compare it against, so a sensor that fell from every-minute to
every-hour reads the same as one that was always quiet. This module supplies the
comparison: the sampling interval the study asked for, converted to records per
hour, so a bucket can be classified rather than merely counted.

The interval comes from the same configs the requirements view reads
(services/sensor_requirements.py), which is why the tables here are keyed the
same way — by stream key, per platform.

**Units are per platform, not per setting name.** The same name carries different
units on the two clients: Android's `frequency_processor` is 60 and means sixty
seconds, iOS's is 60000000 and means the same interval in microseconds. Getting
this wrong is a factor of a million, so each entry states its unit rather than
inferring one from the magnitude. The units are those the Configurator labels its
own fields with (`AWARE-Configurator/reactapp/src/pages/SensorData.jsx`), which is
what a researcher was reading when they chose the value.

**A rate is one row per sample, which not every sensor is.** Three shapes exist:

- *Sampled* — one row per interval. `processor`, `applications`, `timezone`.
  A record count is directly comparable to the configured rate.
- *Scanned* — one row per thing found per scan. `bluetooth` writes a row per
  device in range, `network-traffic` a row per application. The configured
  interval bounds the number of *scans*, so the implied record count is a floor
  and a bucket above it says nothing about whether the scan itself is healthy.
  Marked `floor` so a caller can present the comparison for what it is.
- *Event* — no interval at all. `calls`, `messages`, `screen`: the phone writes
  when something happens, and no configuration predicts how often that is. These
  carry no expectation, so presence is all a bucket of them can be judged on.

A sensor whose governing setting is missing, unparseable or non-positive also
ends up without an expectation. That is reported as `unconfigured` rather than
defaulted to something, because a guessed denominator would classify buckets
against a number nobody chose.
"""

from dataclasses import dataclass
from typing import Any

from app.services import micro_config, study_config

ANDROID = "android"
IOS = "ios"

SECONDS_PER_HOUR = 3600

#: How a configured interval is spelled. Hardware sampling periods are handed to
#: the OS in microseconds; polling loops are configured in seconds; plugins that
#: sync rather than sample are configured in minutes.
MICROSECONDS = "microseconds"
SECONDS = "seconds"
MINUTES = "minutes"

_TO_SECONDS = {
    MICROSECONDS: 1 / 1_000_000,
    SECONDS: 1.0,
    MINUTES: 60.0,
}

#: One row per sample: a count is comparable to the configured rate directly.
SAMPLED = "sampled"
#: One row per thing found per sample, so the implied count is a lower bound.
SCANNED = "scanned"
#: No configured rate exists. Presence is all a bucket can be judged on.
EVENT = "event"


@dataclass(frozen=True)
class RateSpec:
    """Which setting governs a stream's sampling interval, and how to read it."""

    setting: str
    unit: str
    kind: str = SAMPLED
    #: Further settings governing the same table, when several providers write
    #: to it. The fastest one decides the expectation.
    also: tuple[str, ...] = ()


# Android streams with a configured interval. Everything absent from this table
# is an event stream: `calls`, `messages`, `screen`, `touch`, `keyboard`,
# `screentext`, `notes`, `installations`, `battery`, `network`, `telephony`,
# `significant-motion`, `esm`, `esm-scheduler` and the `applications-*` logs all
# write when something happens rather than on a clock.
ANDROID_RATES: dict[str, RateSpec] = {
    "accelerometer": RateSpec("frequency_accelerometer", MICROSECONDS),
    "barometer": RateSpec("frequency_barometer", MICROSECONDS),
    "gravity": RateSpec("frequency_gravity", MICROSECONDS),
    "gyroscope": RateSpec("frequency_gyroscope", MICROSECONDS),
    "light": RateSpec("frequency_light", MICROSECONDS),
    "linear-accelerometer": RateSpec("frequency_linear_accelerometer", MICROSECONDS),
    "magnetometer": RateSpec("frequency_magnetometer", MICROSECONDS),
    "proximity": RateSpec("frequency_proximity", MICROSECONDS),
    "rotation": RateSpec("frequency_rotation", MICROSECONDS),
    "temperature": RateSpec("frequency_temperature", MICROSECONDS),
    # Polling loops, configured in seconds.
    "applications": RateSpec("frequency_applications", SECONDS),
    "processor": RateSpec("frequency_processor", SECONDS),
    "timezone": RateSpec("frequency_timezone", SECONDS),
    "screenshot": RateSpec("capture_time_interval", SECONDS),
    # Three location providers share one table; the fastest enabled one sets the
    # expectation, which is the floor a single provider already guarantees.
    "locations": RateSpec(
        "frequency_location_gps",
        SECONDS,
        also=("frequency_location_network",),
    ),
    # A row per device found, per network interface, per access point.
    "bluetooth": RateSpec("frequency_bluetooth", SECONDS, kind=SCANNED),
    "network-traffic": RateSpec("frequency_network_traffic", SECONDS, kind=SCANNED),
    "wifi": RateSpec("frequency_wifi", SECONDS, kind=SCANNED),
    # Plugins that sample on a slow clock, configured in minutes.
    "plugin-ambient-noise": RateSpec("frequency_plugin_ambient_noise", MINUTES),
    "openweather": RateSpec("plugin_openweather_frequency", MINUTES),
}

# iOS streams. `processor` is the reason this table exists separately: the
# micro-server config carries 60000000 where the Android config carries 60, and
# both mean once a minute.
IOS_RATES: dict[str, RateSpec] = {
    "accelerometer": RateSpec("frequency_accelerometer", MICROSECONDS),
    "barometer": RateSpec("frequency_barometer", MICROSECONDS),
    "gyroscope": RateSpec("frequency_gyroscope", MICROSECONDS),
    "linear-accelerometer": RateSpec("frequency_linear_accelerometer", MICROSECONDS),
    "magnetometer": RateSpec("frequency_magnetometer", MICROSECONDS),
    "rotation": RateSpec("frequency_rotation", MICROSECONDS),
    "processor": RateSpec("frequency_processor", MICROSECONDS),
    "locations": RateSpec("frequency_gps", SECONDS),
    "fused-location": RateSpec("frequency_google_fused_location", SECONDS),
    "activity": RateSpec("frequency_plugin_google_activity_recognition", SECONDS),
    "bluetooth": RateSpec("frequency_bluetooth", SECONDS, kind=SCANNED),
    "wifi": RateSpec("frequency_wifi", SECONDS, kind=SCANNED),
    "plugin-ambient-noise": RateSpec("frequency_plugin_ambient_noise", MINUTES),
    "ambient-noise": RateSpec("frequency_plugin_ambient_noise", MINUTES),
    "contacts": RateSpec("frequency_plugin_contacts", MINUTES),
    "health-kit": RateSpec("frequency_health_kit", MINUTES),
    "pedometer": RateSpec("frequency_ios_pedometer", MINUTES),
    "fitbit": RateSpec("plugin_fitbit_frequency", MINUTES),
    "openweather": RateSpec("plugin_openweather_frequency", MINUTES),
    "ble-heartrate": RateSpec("plugin_ble_heartrate_interval_min", MINUTES),
}

RATES = {ANDROID: ANDROID_RATES, IOS: IOS_RATES}

#: Why a stream has no expectation: no configured interval exists for it at all,
#: or the setting that should carry one is missing or unreadable.
NO_RATE = "event"
UNCONFIGURED = "unconfigured"


@dataclass(frozen=True)
class ExpectedRate:
    """What one stream should deliver in an hour, and how firm that figure is."""

    sensor_key: str
    #: SAMPLED, SCANNED, EVENT or UNCONFIGURED.
    basis: str
    #: Records per hour, or None when nothing can be expected.
    per_hour: float | None = None
    #: The interval the figure came from, in seconds.
    interval_seconds: float | None = None
    #: The setting the interval was read from.
    setting: str | None = None

    @property
    def comparable(self) -> bool:
        """Whether a count can be judged against this at all."""
        return self.per_hour is not None and self.per_hour > 0

    @property
    def is_floor(self) -> bool:
        """Whether the figure is a lower bound rather than an expectation."""
        return self.basis == SCANNED


def _interval_seconds(value: Any, unit: str) -> float | None:
    """A configured interval as seconds, or None when it is not a usable number.

    Values arrive as numbers from the Android config and as strings from the
    micro-server config, so both are accepted. Zero and negatives mean "off" or
    "as fast as possible" depending on the sensor, and neither is a rate a bucket
    can be judged against.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None

    seconds = float(value) * _TO_SECONDS[unit]
    return seconds if seconds > 0 else None


def expected_for(
    platform: str, sensor_key: str, settings: dict[str, Any] | None
) -> ExpectedRate:
    """What `sensor_key` should deliver per hour on `platform`.

    A stream with no entry in the table is an event stream and returns no figure.
    A stream with an entry whose setting is absent or unreadable returns none
    either, marked `unconfigured` so the two are distinguishable — the first is
    how the sensor works, the second is something missing from the config.
    """
    table = RATES.get(platform)
    if table is None:
        raise ValueError(f"Unknown platform: {platform}")

    spec = table.get(sensor_key)
    if spec is None:
        return ExpectedRate(sensor_key=sensor_key, basis=EVENT)

    settings = settings or {}
    candidates = (spec.setting, *spec.also)
    intervals = [
        (name, _interval_seconds(settings.get(name), spec.unit))
        for name in candidates
        if name in settings
    ]
    usable = [(name, seconds) for name, seconds in intervals if seconds is not None]
    if not usable:
        return ExpectedRate(
            sensor_key=sensor_key, basis=UNCONFIGURED, setting=spec.setting
        )

    # The fastest provider decides: a table several providers write to receives
    # at least what the quickest of them produces.
    setting, seconds = min(usable, key=lambda pair: pair[1])

    return ExpectedRate(
        sensor_key=sensor_key,
        basis=spec.kind,
        per_hour=SECONDS_PER_HOUR / seconds,
        interval_seconds=seconds,
        setting=setting,
    )


def rates_for(platform: str, settings: dict[str, Any] | None) -> dict[str, ExpectedRate]:
    """Every stream this platform's table knows about, with its expectation.

    Only the streams with an entry, so a caller holding an arbitrary sensor key
    should reach for `resolved` rather than indexing this directly.
    """
    table = RATES.get(platform)
    if table is None:
        raise ValueError(f"Unknown platform: {platform}")
    return {key: expected_for(platform, key, settings) for key in table}


def resolved(rates: dict[str, ExpectedRate], sensor_key: str) -> ExpectedRate:
    """The expectation for any stream, whether the rate table names it or not.

    Absent from the table *is* the answer for an event sensor, so a caller walking
    every sensor a device reported gets that answer as an `ExpectedRate` carrying
    the `event` basis. Every sensor then arrives with a basis a cell can name.
    """
    return rates.get(sensor_key) or ExpectedRate(sensor_key=sensor_key, basis=EVENT)


def study_rates() -> dict[str, dict[str, ExpectedRate]]:
    """Both platforms' expectations, from the two configs that define them."""
    deployed = study_config.load_deployed_config()
    micro = micro_config.load_micro_config()
    return {
        ANDROID: rates_for(ANDROID, deployed.settings if deployed else None),
        IOS: rates_for(IOS, micro.settings if micro else None),
    }
