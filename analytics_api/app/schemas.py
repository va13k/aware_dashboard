from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int = Field(validation_alias="_id")
    timestamp: float
    device_id: str


class SeriesBucketSchema(BaseModel):
    """One bucket of a server-aggregated sensor series (see services/series.py)."""

    t: float
    avg: float | None = None
    lo: float | None = None
    hi: float | None = None
    n: int


# ---------------------------------------------------------------------------
# Android schemas — flat columns, no JSON blob to resolve
# ---------------------------------------------------------------------------


class AndroidDeviceSchema(_Base):
    board: str | None = None
    device: str | None = None
    build_id: str | None = None
    hardware: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    product: str | None = None
    release: str | None = None
    sdk: str | None = None


class AndroidAccelerometerSchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidApplicationsCrashesSchema(_Base):
    package_name: str | None = None
    application_name: str | None = None
    application_version: float = 0
    error_short: str | None = None
    error_long: str | None = None
    error_condition: int = 0
    is_system_app: int = 0


class AndroidApplicationsForegroundSchema(_Base):
    package_name: str | None = None
    application_name: str | None = None
    is_system_app: int = 0


class AndroidApplicationsHistorySchema(_Base):
    package_name: str | None = None
    application_name: str | None = None
    process_importance: int = 0
    process_id: int = 0
    double_end_timestamp: float = 1
    is_system_app: int = 0


class AndroidApplicationsNotificationsSchema(_Base):
    package_name: str | None = None
    application_name: str | None = None
    text: str | None = None
    sound: str | None = None
    vibrate: str | None = None
    defaults: int = -1
    flags: int = -1


class AndroidBarometerSchema(_Base):
    double_values_0: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidBatterySchema(_Base):
    battery_status: int = 0
    battery_level: int = 0
    battery_scale: int = 0
    battery_voltage: int = 0
    battery_temperature: int = 0
    battery_adaptor: int = 0
    battery_health: int = 0
    battery_technology: str | None = None


class AndroidBatteryChargesSchema(_Base):
    battery_start: int = 0
    battery_end: int = 0
    double_end_timestamp: float = 0


class AndroidBatteryDischargesSchema(_Base):
    battery_start: int = 0
    battery_end: int = 0
    double_end_timestamp: float = 0


class AndroidBluetoothSchema(_Base):
    bt_address: str = ""
    bt_name: str | None = None
    bt_rssi: int = 0
    label: str | None = None


class AndroidCallsSchema(_Base):
    call_type: int = 0
    call_duration: int = 0
    trace: str | None = None


class AndroidEsmsSchema(_Base):
    esm_json: str | None = None
    esm_status: int = 0
    esm_expiration_threshold: int = 0
    esm_notification_timeout: int = 0
    double_esm_user_answer_timestamp: float = 0
    esm_user_answer: str | None = None
    esm_trigger: str | None = None


class AndroidGravitySchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidGyroscopeSchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidInstallationsSchema(_Base):
    package_name: str | None = None
    application_name: str | None = None
    installation_status: int = -1
    version_name: str | None = None
    version_code: int = -1


class AndroidKeyboardSchema(_Base):
    package_name: str | None = None
    before_text: str | None = None
    current_text: str | None = None
    is_password: int = -1


class AndroidLightSchema(_Base):
    double_light_lux: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidLinearAccelerometerSchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidLocationsSchema(_Base):
    double_latitude: float = 0
    double_longitude: float = 0
    double_bearing: float = 0
    double_speed: float = 0
    double_altitude: float = 0
    provider: str | None = None
    accuracy: float = 0
    label: str | None = None


class AndroidMagnetometerSchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidMessagesSchema(_Base):
    message_type: int = 0
    trace: str | None = None


class AndroidNetworkSchema(_Base):
    network_type: int = 0
    network_subtype: str | None = None
    network_state: int = 0


class AndroidNetworkTrafficSchema(_Base):
    network_type: int = 0
    double_received_bytes: float = 0
    double_sent_bytes: float = 0
    double_received_packets: float = 0
    double_sent_packets: float = 0


class AndroidNotesSchema(_Base):
    note: str | None = None


class AndroidPluginAmbientNoiseSchema(_Base):
    double_frequency: float = 0
    double_decibels: float = 0
    double_rms: float = 0
    is_silent: int = 0
    double_silence_threshold: float = 0


class AndroidPluginOpenweatherSchema(_Base):
    city: str | None = None
    temperature: float = 0
    temperature_max: float = 0
    temperature_min: float = 0
    unit: str | None = None
    humidity: float = 0
    pressure: float = 0
    wind_speed: float = 0
    wind_degrees: float = 0
    cloudiness: float = 0
    rain: float = 0
    snow: float = 0
    sunrise: float = 0
    sunset: float = 0
    weather_icon_id: int = 0
    weather_description: str | None = None


class AndroidProximitySchema(_Base):
    double_proximity: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidRotationSchema(_Base):
    double_values_0: float = 0
    double_values_1: float = 0
    double_values_2: float = 0
    double_values_3: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidScreenSchema(_Base):
    screen_status: int = 0


class AndroidScreentextSchema(_Base):
    class_name: str | None = None
    package_name: str | None = None
    text: str | None = None
    user_action: int = 0
    event_type: int = 0


class AndroidSignificantSchema(_Base):
    is_moving: int = 0


class AndroidTelephonySchema(_Base):
    data_enabled: int = 0
    imei_meid_esn: str | None = None
    software_version: str | None = None
    line_number: str | None = None
    network_country_iso_mcc: str | None = None
    network_operator_code: str | None = None
    network_operator_name: str | None = None
    network_type: int = 0
    phone_type: int = 0
    sim_state: int = 0
    sim_operator_code: str | None = None
    sim_operator_name: str | None = None
    sim_serial: str | None = None
    subscriber_id: str | None = None


class AndroidTemperatureSchema(_Base):
    temperature_celsius: float = 0
    accuracy: int = 0
    label: str | None = None


class AndroidTimezoneSchema(_Base):
    timezone: str | None = None


class AndroidTouchSchema(_Base):
    touch_app: str | None = None
    touch_action: str | None = None
    touch_action_text: str | None = None
    scroll_items: int = -1
    scroll_from_index: int = -1
    scroll_to_index: int = -1


class AndroidWifiSchema(_Base):
    bssid: str = ""
    ssid: str | None = None
    security: str | None = None
    frequency: int = 0
    rssi: int = 0
    label: str | None = None


# ---------------------------------------------------------------------------
# iOS schemas — data is a JSON blob; flatten it into the response.
# extra="allow" surfaces every key from the blob even if not explicitly typed.
# ---------------------------------------------------------------------------

IOS_DATA_METADATA_KEYS = frozenset({"_id", "id", "timestamp", "device_id"})


def strip_ios_data_metadata(data: Any) -> dict:
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key not in IOS_DATA_METADATA_KEYS}


class IosSchema(_Base):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="allow",
    )

    @model_validator(mode="before")
    @classmethod
    def flatten_data(cls, v: Any) -> Any:
        if isinstance(v, dict):
            data = strip_ios_data_metadata(v.pop("data", None))
            return {**v, **data}
        # ORM object
        data = strip_ios_data_metadata(getattr(v, "data", None))
        return {
            "_id": getattr(v, "_id", None),
            "timestamp": getattr(v, "timestamp", None),
            "device_id": getattr(v, "device_id", None),
            **data,
        }


# ---------------------------------------------------------------------------
# Study status — derived from aware_studies and the two deployed configs
# ---------------------------------------------------------------------------


class _Derived(BaseModel):
    """Built from the service dataclasses rather than from a table row."""

    model_config = ConfigDict(from_attributes=True)


class AndroidStudyEventSchema(_Derived):
    timestamp: float | None = None
    kind: str
    message: str = ""
    occurrences: int = 1
    joined_at: float | None = None
    updated_at: float | None = None
    exited_at: float | None = None
    approved_consents: list[str] = []
    declined_consents: list[str] = []
    consent_context: str | None = None
    config_id: str | None = None
    config_updated_at: str | None = None


class AndroidStudySummarySchema(_Derived):
    enrollment_status: Literal["in_study", "left_study", "unknown"] = "unknown"
    last_study_event_at: float | None = None
    last_study_event: str | None = None
    last_join_at: float | None = None
    last_exit_at: float | None = None
    last_rejoin_at: float | None = None
    last_rejoin_pause_started_at: float | None = None
    last_rejoin_pause_ms: float | None = None
    config_id: str | None = None
    config_updated_at: str | None = None
    approved_consents: list[str] = []
    declined_consents: list[str] = []
    last_consent_at: float | None = None
    consent_context: Literal["initial", "study_update"] | None = None
    event_count: int = 0
    duplicate_row_count: int = 0


class ConfigDiffRowSchema(_Derived):
    path: str
    kind: Literal["changed", "only_on_server", "only_on_device"]
    server_value: Any = None
    device_value: Any = None


class ConfigDiffSchema(_Derived):
    config_status: Literal["current", "stale", "unknown"] = "unknown"
    status_reason: Literal["no_device_config", "no_server_config"] | None = None
    config_update_enabled: bool = False
    device_config_update_enabled: bool = False
    server_updated_at: str | None = None
    device_updated_at: str | None = None
    diff_count: int = 0
    rows: list[ConfigDiffRowSchema] = []


class AndroidStudyListSummarySchema(_Derived):
    """What a row in the device list needs, without the timeline or the diff."""

    enrollment_status: Literal["in_study", "left_study", "unknown"] = "unknown"
    last_study_event_at: float | None = None
    config_status: Literal["current", "stale", "unknown"] = "unknown"
    diff_count: int = 0


class SensorRequirementSchema(_Derived):
    sensor_key: str
    required: bool
    settings: list[str] = []


class PlatformRequirementsSchema(_Derived):
    platform: Literal["android", "ios"]
    available: bool = False
    sensors: list[SensorRequirementSchema] = []
    required_without_stream: list[str] = []
    unmapped_settings: list[str] = []
    required_sensor_count: int = 0


class StudyRequirementsSchema(BaseModel):
    android: PlatformRequirementsSchema
    ios: PlatformRequirementsSchema
