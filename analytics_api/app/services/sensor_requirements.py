"""Maps study-config settings to the sensor streams the API exposes.

A study config toggles settings; the dashboard requests data by stream key. This
module holds the table between the two, one per platform. The relationship is
many-to-many: the three location toggles all feed `locations`, and
`status_battery` feeds three streams.

Settings with no stream behind them are listed in `required_without_stream` when
enabled. Settings the table does not contain are listed in `unmapped_settings`.
Stream keys the table does not contain are not returned at all; the frontend
holds the list of streams it can render and treats an absent key as one the
config does not govern.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services import micro_config, study_config

ANDROID = "android"
IOS = "ios"

#: Settings with no stream the dashboard can request: no table in the schema, a
#: table with no API route, or a setting that governs transport rather than a
#: sensor.
NO_STREAM: tuple[str, ...] = ()

# Android settings, from studies/studyConfig.json. Stream keys are the ones the
# API routes under /android/{device_id}/.
ANDROID_SETTING_STREAMS: dict[str, tuple[str, ...]] = {
    "status_accelerometer": ("accelerometer",),
    # The applications sensor writes the foreground log and the usage history.
    "status_applications": ("applications", "applications-history"),
    "status_barometer": ("barometer",),
    "status_battery": ("battery", "battery-charges", "battery-discharges"),
    "status_bluetooth": ("bluetooth",),
    "status_calls": ("calls",),
    "status_communication_events": ("calls", "messages"),
    "status_crashes": ("applications-crashes",),
    "status_esm": ("esm",),
    "status_gravity": ("gravity",),
    "status_gyroscope": ("gyroscope",),
    "status_installations": ("installations",),
    "status_keyboard": ("keyboard",),
    "status_light": ("light",),
    "status_linear_accelerometer": ("linear-accelerometer",),
    # Three location providers, one table.
    "status_location_gps": ("locations",),
    "status_location_network": ("locations",),
    "status_location_passive": ("locations",),
    "status_magnetometer": ("magnetometer",),
    "status_messages": ("messages",),
    "status_network_events": ("network",),
    "status_network_traffic": ("network-traffic",),
    "status_notes": ("notes",),
    "status_notifications": ("applications-notifications",),
    "status_plugin_ambient_noise": ("plugin-ambient-noise",),
    "status_plugin_esm_scheduler": ("esm-scheduler",),
    "status_plugin_openweather": ("openweather",),
    "status_processor": ("processor",),
    "status_screenshot": ("screenshot",),
    "status_screenshot_local_storage": NO_STREAM,
    "status_proximity": ("proximity",),
    "status_rotation": ("rotation",),
    "status_screen": ("screen",),
    "status_screentext": ("screentext",),
    # Present in the Android config; no table in this deployment's schema.
    "status_google_fused_location": NO_STREAM,
    "status_plugin_contacts": NO_STREAM,
    "status_plugin_device_usage": NO_STREAM,
    "status_plugin_fitbit": NO_STREAM,
    "status_plugin_google_activity_recognition": NO_STREAM,
    "status_plugin_studentlife_audio": NO_STREAM,
    # Sign-in setting.
    "status_plugin_google_login": NO_STREAM,
    "status_significant_motion": ("significant-motion",),
    "status_telephony": ("telephony",),
    "status_temperature": ("temperature",),
    "status_timezone": ("timezone",),
    "status_touch": ("touch",),
    "status_wifi": ("wifi",),
    # Transport settings: how data leaves the phone.
    "status_mqtt": NO_STREAM,
    "status_webservice": NO_STREAM,
}

# iOS settings, from the micro-server config. Its sensor group names do not
# always match the setting name - the `communication` group carries
# `status_calls` - so this table is keyed on the settings the file declares.
IOS_SETTING_STREAMS: dict[str, tuple[str, ...]] = {
    "status_accelerometer": ("accelerometer",),
    "status_barometer": ("barometer",),
    "status_battery": ("battery", "battery-charges", "battery-discharges"),
    "status_bluetooth": ("bluetooth",),
    "status_calls": ("calls",),
    "status_gyroscope": ("gyroscope",),
    "status_health_kit": (
        "health-kit",
        "health-kit/category",
        "health-kit/quantity",
        "health-kit/workout",
    ),
    "status_google_fused_location": ("fused-location",),
    "status_linear_accelerometer": ("linear-accelerometer",),
    "status_location_gps": ("locations",),
    "status_magnetometer": ("magnetometer",),
    "status_network_events": ("network",),
    "status_plugin_ambient_noise": ("plugin-ambient-noise",),
    "status_plugin_ble_heartrate": ("ble-heartrate",),
    "status_plugin_calendar": ("calendar",),
    "status_plugin_contacts": ("contacts",),
    "status_plugin_device_usage": ("device-usage",),
    # The Google Calendar-based scheduler.
    "status_plugin_esm_scheduler": ("esm-scheduler",),
    "status_plugin_fitbit": ("fitbit", "fitbit-data", "fitbit-device"),
    "status_plugin_google_activity_recognition": ("activity",),
    "status_plugin_headphone_motion": ("headphone-motion",),
    # The iOS scheduler, which fills the answers table.
    "status_plugin_ios_esm": ("esm-scheduler", "esm"),
    "status_plugin_ios_pedometer": ("pedometer",),
    "status_plugin_ntptime": ("ntptime",),
    "status_plugin_openweather": ("openweather",),
    "status_plugin_studentlife_audio": ("studentlife-audio",),
    # Spelled this way in the micro-server config.
    "status_push_notication": ("push-notification",),
    "status_processor": ("processor",),
    "status_rotation": ("rotation",),
    "status_screen": ("screen",),
    "status_significant_motion": ("significant-motion",),
    "status_timezone": ("timezone",),
    "status_wifi": ("wifi",),
}

SETTING_STREAMS = {ANDROID: ANDROID_SETTING_STREAMS, IOS: IOS_SETTING_STREAMS}

STATUS_PREFIX = "status_"


@dataclass(frozen=True)
class SensorRequirement:
    sensor_key: str
    required: bool
    #: The settings that govern this stream.
    settings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlatformRequirements:
    platform: str
    #: False when no config was found for this platform.
    available: bool = False
    sensors: list[SensorRequirement] = field(default_factory=list)
    #: Enabled settings with no stream the dashboard can request.
    required_without_stream: list[str] = field(default_factory=list)
    #: `status_*` settings this table does not know about.
    unmapped_settings: list[str] = field(default_factory=list)
    required_sensor_count: int = 0


def requirements_for(
    platform: str, settings: dict[str, Any] | None
) -> PlatformRequirements:
    """The streams this study configures a phone of that platform to record."""
    table = SETTING_STREAMS.get(platform)
    if table is None:
        raise ValueError(f"Unknown platform: {platform}")
    if not settings:
        return PlatformRequirements(platform=platform)

    governed_by: dict[str, list[str]] = {}
    required_keys: set[str] = set()
    without_stream: list[str] = []

    for name, streams in table.items():
        enabled = name in settings and study_config.is_enabled(settings[name])
        if not streams:
            if enabled:
                without_stream.append(name)
            continue
        for key in streams:
            governed_by.setdefault(key, []).append(name)
            if enabled:
                required_keys.add(key)

    sensors = [
        SensorRequirement(
            sensor_key=key,
            required=key in required_keys,
            settings=sorted(names),
        )
        for key, names in sorted(governed_by.items())
    ]

    unmapped = sorted(
        name
        for name in settings
        if name.startswith(STATUS_PREFIX) and name not in table
    )

    return PlatformRequirements(
        platform=platform,
        available=True,
        sensors=sensors,
        required_without_stream=sorted(without_stream),
        unmapped_settings=unmapped,
        required_sensor_count=len(required_keys),
    )


def study_requirements() -> dict[str, PlatformRequirements]:
    """Requirements for both platforms, from the two configs that define them."""
    deployed = study_config.load_deployed_config()
    micro = micro_config.load_micro_config()
    return {
        ANDROID: requirements_for(ANDROID, deployed.settings if deployed else None),
        IOS: requirements_for(IOS, micro.settings if micro else None),
    }
