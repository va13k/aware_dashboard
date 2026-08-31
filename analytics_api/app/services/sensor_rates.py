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
- *Gated* — an interval exists, but the client drops samples before writing them.
  A positive `threshold_<sensor>` discards a reading too close to the one before
  it, and `status_significant_motion` stops the five motion sensors writing
  anything while the phone is still. Either makes the configured rate a ceiling
  the count sits somewhere under, by an amount no configuration predicts, so
  these are judged on presence like an event sensor, with the figure kept for
  context.

The comparison is one-sided in the other direction too. `frequency_*` reaches
Android as a sampling *hint*, so a phone may deliver faster than asked unless the
study also sets `frequency_<sensor>_enforce`. A bucket above its expectation is
therefore ordinary, which is why `over` is a band rather than a fault.

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
#: An interval exists, but the client filters samples before writing them, so the
#: figure bounds the count from above. Judged on presence, like an event sensor.
GATED = "gated"


@dataclass(frozen=True)
class RateSpec:
    """Which setting governs a stream's sampling interval, and how to read it."""

    setting: str
    unit: str
    kind: str = SAMPLED
    #: Further settings governing the same table, when several providers write
    #: to it. The fastest one decides the expectation.
    also: tuple[str, ...] = ()
    #: A setting whose positive value makes the client discard a reading too
    #: close to the one before it, so the table receives fewer rows than the
    #: interval implies.
    threshold: str | None = None


# Android streams with a configured interval. Everything absent from this table
# is an event stream: `calls`, `messages`, `screen`, `touch`, `keyboard`,
# `screentext`, `notes`, `installations`, `battery`, `network`, `telephony`,
# `significant-motion`, `esm`, `esm-scheduler` and the `applications-*` logs all
# write when something happens rather than on a clock.
ANDROID_RATES: dict[str, RateSpec] = {
    "accelerometer": RateSpec(
        "frequency_accelerometer", MICROSECONDS, threshold="threshold_accelerometer"
    ),
    "barometer": RateSpec(
        "frequency_barometer", MICROSECONDS, threshold="threshold_barometer"
    ),
    "gravity": RateSpec(
        "frequency_gravity", MICROSECONDS, threshold="threshold_gravity"
    ),
    "gyroscope": RateSpec(
        "frequency_gyroscope", MICROSECONDS, threshold="threshold_gyroscope"
    ),
    "light": RateSpec("frequency_light", MICROSECONDS, threshold="threshold_light"),
    "linear-accelerometer": RateSpec(
        "frequency_linear_accelerometer",
        MICROSECONDS,
        threshold="threshold_linear_accelerometer",
    ),
    "magnetometer": RateSpec(
        "frequency_magnetometer", MICROSECONDS, threshold="threshold_magnetometer"
    ),
    "proximity": RateSpec(
        "frequency_proximity", MICROSECONDS, threshold="threshold_proximity"
    ),
    "rotation": RateSpec(
        "frequency_rotation", MICROSECONDS, threshold="threshold_rotation"
    ),
    "temperature": RateSpec(
        "frequency_temperature", MICROSECONDS, threshold="threshold_temperature"
    ),
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

#: With `status_significant_motion` on, these five write only while the phone is
#: moving (`com.aware.Accelerometer#onSensorChanged` and its four siblings return
#: early otherwise), so an hour of stillness is an empty bucket the study asked
#: for. Android only: iOS carries the setting as a sensor of its own, gating
#: nothing else.
MOTION_SETTING = "status_significant_motion"
MOTION_GATED = frozenset(
    {"accelerometer", "gravity", "gyroscope", "linear-accelerometer", "rotation"}
)

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
    #: The settings filtering this stream on the phone, when any do. Named rather
    #: than counted, because the setting is what a researcher changes once they
    #: know why a row is going unjudged.
    gated_by: tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        """Whether a count can be judged against this at all."""
        return self.basis in (SAMPLED, SCANNED) and (self.per_hour or 0) > 0

    @property
    def is_floor(self) -> bool:
        """Whether the figure is a lower bound rather than an expectation."""
        return self.basis == SCANNED

    @property
    def is_ceiling(self) -> bool:
        """Whether the figure is an upper bound rather than an expectation."""
        return self.basis == GATED


def _positive_number(value: Any) -> float | None:
    """A config value as a positive number, or None when it is not one.

    Values arrive as numbers from the Android config and as strings from the
    micro-server config, so both are accepted. Zero and negatives mean "off" or
    "as fast as possible" depending on the setting, and neither is a figure an
    interval or a threshold can be read from.
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
    return float(value) if value > 0 else None


def _interval_seconds(value: Any, unit: str) -> float | None:
    """A configured interval as seconds, or None when it is not a usable number."""
    number = _positive_number(value)
    if number is None:
        return None

    seconds = number * _TO_SECONDS[unit]
    return seconds if seconds > 0 else None


def _gates(
    platform: str, sensor_key: str, spec: RateSpec, settings: dict[str, Any]
) -> tuple[str, ...]:
    """The settings filtering this stream on the phone, if any do.

    A gate does not change how often the sensor samples; it decides which samples
    reach the table. The interval therefore still bounds the count, and nothing
    predicts how far under it the filter leaves things.
    """
    gates = []
    if spec.threshold and _positive_number(settings.get(spec.threshold)) is not None:
        gates.append(spec.threshold)
    if (
        platform == ANDROID
        and sensor_key in MOTION_GATED
        and study_config.is_enabled(settings.get(MOTION_SETTING))
    ):
        gates.append(MOTION_SETTING)
    return tuple(gates)


def expected_for(
    platform: str, sensor_key: str, settings: dict[str, Any] | None
) -> ExpectedRate:
    """What `sensor_key` should deliver per hour on `platform`.

    A stream with no entry in the table is an event stream and returns no figure.
    A stream with an entry whose setting is absent or unreadable returns none
    either, marked `unconfigured` so the two are distinguishable — the first is
    how the sensor works, the second is something missing from the config.

    A stream the config also filters on the phone keeps its figure and is marked
    `gated`: the rate is then a ceiling rather than an expectation, so the count
    is not comparable with it.
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
    gates = _gates(platform, sensor_key, spec, settings)

    return ExpectedRate(
        sensor_key=sensor_key,
        basis=GATED if gates else spec.kind,
        per_hour=SECONDS_PER_HOUR / seconds,
        interval_seconds=seconds,
        setting=setting,
        gated_by=gates,
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
