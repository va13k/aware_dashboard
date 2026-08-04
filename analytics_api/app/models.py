from sqlalchemy import BigInteger, Column, Double, Integer, JSON, String, Text
from app.database import AndroidBase, IosBase

# ---------------------------------------------------------------------------
# Android models — each table has its own explicit columns
# ---------------------------------------------------------------------------


class AndroidDevice(AndroidBase):
    __tablename__ = "aware_device"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    board = Column(Text)
    device = Column(Text)
    build_id = Column(Text)
    hardware = Column(Text)
    manufacturer = Column(Text)
    model = Column(Text)
    product = Column(Text)
    release = Column(Text)
    sdk = Column(Text)


class AndroidAwareStudy(AndroidBase):
    """Study lifecycle events: joins, updates, consent, exits.

    Not a sensor stream - one row per event the client reports about its own
    study membership. The client writes a new row per event and never updates,
    so logically identical events appear more than once with different `_id`
    values; readers have to deduplicate.

    `study_config` is the config the phone carries, and it holds the participant
    and root database credentials in full. It must never be serialised into a
    response - see app.services.study_config for the redacted view.
    """

    __tablename__ = "aware_studies"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    study_url = Column(Text)
    study_key = Column(Integer, default=-1)
    study_api = Column(Text)
    study_pi = Column(Text)
    study_config = Column(Text)
    study_title = Column(Text)
    study_description = Column(Text)
    double_join = Column(Double, default=0)
    double_updated = Column(Double, default=0)
    double_exit = Column(Double, default=0)
    study_compliance = Column(Text)


class AndroidAccelerometer(AndroidBase):
    __tablename__ = "accelerometer"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidApplicationsCrashes(AndroidBase):
    __tablename__ = "applications_crashes"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    application_name = Column(Text)
    application_version = Column(Double, default=0)
    error_short = Column(Text)
    error_long = Column(Text)
    error_condition = Column(Integer, default=0)
    is_system_app = Column(Integer, default=0)


class AndroidApplicationsForeground(AndroidBase):
    __tablename__ = "applications_foreground"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    application_name = Column(Text)
    is_system_app = Column(Integer, default=0)


class AndroidApplicationsHistory(AndroidBase):
    __tablename__ = "applications_history"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    application_name = Column(Text)
    process_importance = Column(Integer, default=0)
    process_id = Column(Integer, default=0)
    double_end_timestamp = Column(Double, default=1)
    is_system_app = Column(Integer, default=0)


class AndroidApplicationsNotifications(AndroidBase):
    __tablename__ = "applications_notifications"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    application_name = Column(Text)
    text = Column(Text)
    sound = Column(Text)
    vibrate = Column(Text)
    defaults = Column(Integer, default=-1)
    flags = Column(Integer, default=-1)


class AndroidBarometer(AndroidBase):
    __tablename__ = "barometer"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidBattery(AndroidBase):
    __tablename__ = "battery"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    battery_status = Column(Integer, default=0)
    battery_level = Column(Integer, default=0)
    battery_scale = Column(Integer, default=0)
    battery_voltage = Column(Integer, default=0)
    battery_temperature = Column(Integer, default=0)
    battery_adaptor = Column(Integer, default=0)
    battery_health = Column(Integer, default=0)
    battery_technology = Column(Text)


class AndroidBatteryCharges(AndroidBase):
    __tablename__ = "battery_charges"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    battery_start = Column(Integer, default=0)
    battery_end = Column(Integer, default=0)
    double_end_timestamp = Column(Double, default=0)


class AndroidBatteryDischarges(AndroidBase):
    __tablename__ = "battery_discharges"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    battery_start = Column(Integer, default=0)
    battery_end = Column(Integer, default=0)
    double_end_timestamp = Column(Double, default=0)


class AndroidBluetooth(AndroidBase):
    __tablename__ = "bluetooth"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    bt_address = Column(String(150), default="")
    bt_name = Column(Text)
    bt_rssi = Column(Integer, default=0)
    label = Column(Text)


class AndroidCalls(AndroidBase):
    __tablename__ = "calls"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    call_type = Column(Integer, default=0)
    call_duration = Column(Integer, default=0)
    trace = Column(Text)


class AndroidEsms(AndroidBase):
    __tablename__ = "esms"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    esm_json = Column(Text)
    esm_status = Column(Integer, default=0)
    esm_expiration_threshold = Column(Integer, default=0)
    esm_notification_timeout = Column(Integer, default=0)
    double_esm_user_answer_timestamp = Column(Double, default=0)
    esm_user_answer = Column(Text)
    esm_trigger = Column(Text)


class AndroidGravity(AndroidBase):
    __tablename__ = "gravity"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidGyroscope(AndroidBase):
    __tablename__ = "gyroscope"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidInstallations(AndroidBase):
    __tablename__ = "installations"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    application_name = Column(Text)
    installation_status = Column(Integer, default=-1)
    version_name = Column(Text)
    version_code = Column(Integer, default=-1)


class AndroidKeyboard(AndroidBase):
    __tablename__ = "keyboard"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    package_name = Column(Text)
    before_text = Column(Text)
    current_text = Column(Text)
    is_password = Column(Integer, default=-1)


class AndroidLight(AndroidBase):
    __tablename__ = "light"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_light_lux = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidLinearAccelerometer(AndroidBase):
    __tablename__ = "linear_accelerometer"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidLocations(AndroidBase):
    __tablename__ = "locations"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_latitude = Column(Double, default=0)
    double_longitude = Column(Double, default=0)
    double_bearing = Column(Double, default=0)
    double_speed = Column(Double, default=0)
    double_altitude = Column(Double, default=0)
    provider = Column(Text)
    accuracy = Column(Double, default=0)
    label = Column(Text)


class AndroidMagnetometer(AndroidBase):
    __tablename__ = "magnetometer"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidMessages(AndroidBase):
    __tablename__ = "messages"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    message_type = Column(Integer, default=0)
    trace = Column(Text)


class AndroidNetwork(AndroidBase):
    __tablename__ = "network"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    network_type = Column(Integer, default=0)
    network_subtype = Column(Text)
    network_state = Column(Integer, default=0)


class AndroidNetworkTraffic(AndroidBase):
    __tablename__ = "network_traffic"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    network_type = Column(Integer, default=0)
    double_received_bytes = Column(Double, default=0)
    double_sent_bytes = Column(Double, default=0)
    double_received_packets = Column(Double, default=0)
    double_sent_packets = Column(Double, default=0)


class AndroidNotes(AndroidBase):
    __tablename__ = "notes"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    note = Column(Text)


class AndroidPluginAmbientNoise(AndroidBase):
    __tablename__ = "plugin_ambient_noise"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_frequency = Column(Double, default=0)
    double_decibels = Column(Double, default=0)
    double_rms = Column(Double, default=0)
    is_silent = Column(Integer, default=0)
    double_silence_threshold = Column(Double, default=0)


class AndroidPluginOpenweather(AndroidBase):
    __tablename__ = "plugin_openweather"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    city = Column(Text)
    temperature = Column(Double, default=0)
    temperature_max = Column(Double, default=0)
    temperature_min = Column(Double, default=0)
    unit = Column(Text)
    humidity = Column(Double, default=0)
    pressure = Column(Double, default=0)
    wind_speed = Column(Double, default=0)
    wind_degrees = Column(Double, default=0)
    cloudiness = Column(Double, default=0)
    rain = Column(Double, default=0)
    snow = Column(Double, default=0)
    sunrise = Column(Double, default=0)
    sunset = Column(Double, default=0)
    weather_icon_id = Column(Integer, default=0)
    weather_description = Column(Text)


class AndroidProximity(AndroidBase):
    __tablename__ = "proximity"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_proximity = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidRotation(AndroidBase):
    __tablename__ = "rotation"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    double_values_0 = Column(Double, default=0)
    double_values_1 = Column(Double, default=0)
    double_values_2 = Column(Double, default=0)
    double_values_3 = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidScreen(AndroidBase):
    __tablename__ = "screen"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    screen_status = Column(Integer, default=0)


class AndroidScreentext(AndroidBase):
    __tablename__ = "screentext"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    class_name = Column(String(150), default="")
    package_name = Column(String(150), default="")
    text = Column(Text)
    user_action = Column(Integer, default=0)
    event_type = Column(Integer, default=0)


class AndroidSignificant(AndroidBase):
    __tablename__ = "significant"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    is_moving = Column(Integer, default=0)


class AndroidTelephony(AndroidBase):
    __tablename__ = "telephony"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    data_enabled = Column(Integer, default=0)
    imei_meid_esn = Column(Text)
    software_version = Column(Text)
    line_number = Column(Text)
    network_country_iso_mcc = Column(Text)
    network_operator_code = Column(Text)
    network_operator_name = Column(Text)
    network_type = Column(Integer, default=0)
    phone_type = Column(Integer, default=0)
    sim_state = Column(Integer, default=0)
    sim_operator_code = Column(Text)
    sim_operator_name = Column(Text)
    sim_serial = Column(Text)
    subscriber_id = Column(Text)


class AndroidTemperature(AndroidBase):
    __tablename__ = "temperature"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    temperature_celsius = Column(Double, default=0)
    accuracy = Column(Integer, default=0)
    label = Column(Text)


class AndroidTimezone(AndroidBase):
    __tablename__ = "timezone"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    timezone = Column(Text)


class AndroidTouch(AndroidBase):
    __tablename__ = "touch"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    touch_app = Column(Text)
    touch_action = Column(Text)
    touch_action_text = Column(Text)
    scroll_items = Column(Integer, default=-1)
    scroll_from_index = Column(Integer, default=-1)
    scroll_to_index = Column(Integer, default=-1)


class AndroidWifi(AndroidBase):
    __tablename__ = "wifi"
    _id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(Double, default=0)
    device_id = Column(String(150), default="")
    bssid = Column(String(255), default="")
    ssid = Column(Text)
    security = Column(Text)
    frequency = Column(Integer, default=0)
    rssi = Column(Integer, default=0)
    label = Column(Text)


# ---------------------------------------------------------------------------
# iOS models — all tables share (_id, timestamp, device_id, data JSON).
# A factory avoids repeating the same 4 columns for every table.
# ---------------------------------------------------------------------------


def _ios_model(table_name: str):
    return type(
        f"Ios{table_name.replace('_', ' ').title().replace(' ', '')}",
        (IosBase,),
        {
            "__tablename__": table_name,
            "_id": Column(Integer, primary_key=True, autoincrement=True),
            "timestamp": Column(Double, nullable=False),
            "device_id": Column(String(128), nullable=False),
            "data": Column(JSON, nullable=False),
        },
    )


# Core sensors
IosAccelerometer = _ios_model("accelerometer")
IosBarometer = _ios_model("barometer")
IosBattery = _ios_model("battery")
IosBatteryCharges = _ios_model("battery_charges")
IosBatteryDischarges = _ios_model("battery_discharges")
IosBluetooth = _ios_model("bluetooth")
IosCalls = _ios_model("calls")
IosCommunication = _ios_model("communication")
IosEsm = _ios_model("esm")
IosGyroscope = _ios_model("gyroscope")
IosLinearAccelerometer = _ios_model("linear_accelerometer")
IosLocations = _ios_model("locations")
IosMagnetometer = _ios_model("magnetometer")
IosNetwork = _ios_model("network")
IosProcessor = _ios_model("processor")
IosProximity = _ios_model("proximity")
IosRotation = _ios_model("rotation")
IosScreen = _ios_model("screen")
IosSignificantMotion = _ios_model("significant_motion")
IosSensorWifi = _ios_model("sensor_wifi")
IosTimezone = _ios_model("timezone")
IosWifi = _ios_model("wifi")

# System / device tables
IosDevice = _ios_model("aware_device")
IosPushNotification = _ios_model("push_notification")
IosMemory = _ios_model("memory")

# Location extras
IosGoogleFusedLocation = _ios_model("google_fused_location")
IosLocationVisit = _ios_model("ios_location_visit")

# Plugins
IosPluginAmbientNoise = _ios_model("plugin_ambient_noise")
IosPluginBleHeartrate = _ios_model("plugin_ble_heartrate")
IosPluginCalendar = _ios_model("plugin_calendar")
IosPluginCalendarEsmScheduler = _ios_model("plugin_calendar_esm_scheduler")
IosPluginContacts = _ios_model("plugin_contacts")
IosPluginDeviceUsage = _ios_model("plugin_device_usage")
IosPluginFitbit = _ios_model("plugin_fitbit")
IosFitbitData = _ios_model("fitbit_data")
IosFitbitDevice = _ios_model("fitbit_device")
IosPluginHeadphoneMotion = _ios_model("plugin_headphone_motion")
IosPluginActivityRecognition = _ios_model("plugin_ios_activity_recognition")
IosPluginIosEsm = _ios_model("plugin_ios_esm")
IosPedometer = _ios_model("plugin_ios_pedometer")
IosPluginNtptime = _ios_model("plugin_ntptime")
IosPluginOpenweather = _ios_model("plugin_openweather")
IosPluginStudentlifeAudio = _ios_model("plugin_studentlife_audio")

# HealthKit
IosHealthKit = _ios_model("health_kit")
IosHealthKitCategory = _ios_model("health_kit_category")
IosHealthKitQuantity = _ios_model("health_kit_quantity")
IosHealthKitWorkout = _ios_model("health_kit_workout")
