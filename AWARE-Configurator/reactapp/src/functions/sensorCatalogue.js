import AccessTime from "@mui/icons-material/AccessTime";
import AccountCircle from "@mui/icons-material/AccountCircle";
import Apps from "@mui/icons-material/Apps";
import ArrowDownward from "@mui/icons-material/ArrowDownward";
import BatteryFull from "@mui/icons-material/BatteryFull";
import Bluetooth from "@mui/icons-material/Bluetooth";
import CalendarMonth from "@mui/icons-material/CalendarMonth";
import Call from "@mui/icons-material/Call";
import Compress from "@mui/icons-material/Compress";
import Contacts from "@mui/icons-material/Contacts";
import DirectionsRun from "@mui/icons-material/DirectionsRun";
import DirectionsWalk from "@mui/icons-material/DirectionsWalk";
import EventNote from "@mui/icons-material/EventNote";
import Explore from "@mui/icons-material/Explore";
import FavoriteBorder from "@mui/icons-material/FavoriteBorder";
import GraphicEq from "@mui/icons-material/GraphicEq";
import Headphones from "@mui/icons-material/Headphones";
import Hiking from "@mui/icons-material/Hiking";
import InstallMobile from "@mui/icons-material/InstallMobile";
import LightMode from "@mui/icons-material/LightMode";
import LocationOn from "@mui/icons-material/LocationOn";
import Memory from "@mui/icons-material/Memory";
import MobileFriendly from "@mui/icons-material/MobileFriendly";
import MonitorHeart from "@mui/icons-material/MonitorHeart";
import MyLocation from "@mui/icons-material/MyLocation";
import NetworkCheck from "@mui/icons-material/NetworkCheck";
import NoteAlt from "@mui/icons-material/NoteAlt";
import NotificationsActive from "@mui/icons-material/NotificationsActive";
import Quiz from "@mui/icons-material/Quiz";
import RecordVoiceOver from "@mui/icons-material/RecordVoiceOver";
import RotateRight from "@mui/icons-material/RotateRight";
import Schedule from "@mui/icons-material/Schedule";
import ScreenshotMonitor from "@mui/icons-material/ScreenshotMonitor";
import Sensors from "@mui/icons-material/Sensors";
import SignalCellularAlt from "@mui/icons-material/SignalCellularAlt";
import Smartphone from "@mui/icons-material/Smartphone";
import Speed from "@mui/icons-material/Speed";
import Straighten from "@mui/icons-material/Straighten";
import Thermostat from "@mui/icons-material/Thermostat";
import ThreeDRotation from "@mui/icons-material/ThreeDRotation";
import Watch from "@mui/icons-material/Watch";
import WbSunny from "@mui/icons-material/WbSunny";
import Wifi from "@mui/icons-material/Wifi";

/**
 * Every sensor a study can collect, as data rather than as markup.
 *
 * `settings` names the block that renders a sensor's own options; a sensor with
 * none is not misconfigured, it simply has nothing to decide beyond being on.
 * `platform` is what the clients actually implement, not a hint: a field the
 * Android client does not read cannot be collected by naming it here.
 */

export const SENSOR_ICONS = {
  AccessTime,
  AccountCircle,
  Apps,
  ArrowDownward,
  BatteryFull,
  Bluetooth,
  CalendarMonth,
  Call,
  Compress,
  Contacts,
  DirectionsRun,
  DirectionsWalk,
  EventNote,
  Explore,
  FavoriteBorder,
  GraphicEq,
  Headphones,
  Hiking,
  InstallMobile,
  LightMode,
  LocationOn,
  Memory,
  MobileFriendly,
  MonitorHeart,
  MyLocation,
  NetworkCheck,
  NoteAlt,
  NotificationsActive,
  Quiz,
  RecordVoiceOver,
  RotateRight,
  Schedule,
  ScreenshotMonitor,
  Sensors,
  SignalCellularAlt,
  Smartphone,
  Speed,
  Straighten,
  Thermostat,
  ThreeDRotation,
  Watch,
  WbSunny,
  Wifi,
};

export const SENSORS = [
  {
    name: "Battery",
    description:
      "Battery information and power related events (phone shutting down, rebooting).",
    field: "sensor_battery",
    platform: "both",
    group: "both",
    icon: "BatteryFull",
    settings: null,
  },
  {
    name: "Communication (Calls)",
    description:
      "Call events on iPhone and Android. Android-only communication events and text messages can be controlled below.",
    field: "sensor_communication",
    platform: "both",
    group: "both",
    icon: "Call",
    settings: "SensorCommunicationSubContent",
  },
  {
    name: "Screen",
    description:
      "Smartphone screen status; turning on, turning off, lock, and unlock.",
    field: "sensor_screen",
    platform: "both",
    group: "both",
    icon: "Smartphone",
    settings: "SensorScreenSubContent",
  },
  {
    name: "Timezone",
    description: "Logs user's current timezone.",
    field: "sensor_timezone",
    platform: "both",
    group: "both",
    icon: "Schedule",
    settings: "SensorTimezoneSubContent",
  },
  {
    name: "Accelerometer",
    description:
      "Acceleration applied to the device, including the force of gravity.",
    field: "sensor_accelerometer",
    platform: "both",
    group: "both",
    icon: "Speed",
    settings: "SensorAccelerometerSubContent",
  },
  {
    name: "Barometer",
    description: "Ambient air pressure.",
    field: "sensor_barometer",
    platform: "both",
    group: "both",
    icon: "Compress",
    settings: "SensorBarometerSubContent",
  },
  {
    name: "Bluetooth",
    description:
      "Smartphone's Bluetooth sensor and surrounding Bluetooth-enabled and visible devices. Includes respective RSSI dB values.",
    field: "sensor_bluetooth",
    platform: "both",
    group: "both",
    icon: "Bluetooth",
    settings: "SensorBluetoothSubContent",
  },
  {
    name: "Gyroscope",
    description:
      "Rate or rotation in rad/s around a device\u2019s x-, y-, and z-axis.",
    field: "sensor_gyroscope",
    platform: "both",
    group: "both",
    icon: "ThreeDRotation",
    settings: "SensorGyroscopeSubContent",
  },
  {
    name: "Linear accelerometer",
    description:
      "Acceleration applied to the device, excluding the force of gravity.",
    field: "sensor_linear_accelerometer",
    platform: "both",
    group: "both",
    icon: "Straighten",
    settings: "SensorLinearAccelerometerSubContent",
  },
  {
    name: "Locations",
    description:
      "Best location estimate of the users\u2019 current location, based on an algorithm that results in minimum battery impact.",
    field: "sensor_locations",
    platform: "both",
    group: "both",
    icon: "LocationOn",
    settings: "SensorLocationsSubContent",
  },
  {
    name: "Magnetometer",
    description: "Geomagnetic field strength around the device.",
    field: "sensor_magnetometer",
    platform: "both",
    group: "both",
    icon: "Explore",
    settings: "SensorMagnetometerSubContent",
  },
  {
    name: "Network",
    description:
      "Information on the network sensors availability of the device. These include use of airplane mode, Wi-Fi, Bluetooth, GPS, mobile, and WIMAX status as well as internet availability.",
    field: "sensor_network",
    platform: "both",
    group: "both",
    icon: "NetworkCheck",
    settings: "SensorNetworkSubContent",
  },
  {
    name: "Processor",
    description: "Processor load.",
    field: "sensor_processor",
    platform: "both",
    group: "both",
    icon: "Memory",
    settings: "SensorProcessorSubContent",
  },
  {
    name: "Rotation",
    description:
      "Orientation of the device as a combination of an angle and an axis.",
    field: "sensor_rotation",
    platform: "both",
    group: "both",
    icon: "RotateRight",
    settings: "SensorRotationSubContent",
  },
  {
    name: "Significant Motion",
    description: "Motion co-processor signal for significant movement changes.",
    field: "ios_significant_motion",
    platform: "both",
    group: "both",
    icon: "DirectionsRun",
    settings: null,
  },
  {
    name: "Wi-Fi",
    description:
      "The device\u2019s Wi-Fi sensor, current AP, and surrounding Wi-Fi visible devices with respective RSSI dB values.",
    field: "sensor_wifi",
    platform: "both",
    group: "both",
    icon: "Wifi",
    settings: "SensorWifiSubContent",
  },
  {
    name: "Gravity",
    description:
      "Force of gravity applied to the device, provides a three dimensional vector indicating the direction and magnitude of gravity.",
    field: "sensor_gravity",
    platform: "android",
    group: "android",
    icon: "ArrowDownward",
    settings: "SensorGravitySubContent",
  },
  {
    name: "Light",
    description: "Level of ambient light.",
    field: "sensor_light",
    platform: "android",
    group: "android",
    icon: "LightMode",
    settings: "SensorLightSubContent",
  },
  {
    name: "Proximity",
    description: "Android-only proximity sensor (near/far).",
    field: "sensor_proximity",
    platform: "android",
    group: "android",
    icon: "Sensors",
    settings: "SensorProximitySubContent",
  },
  {
    name: "Temperature",
    description:
      "Ambient air temperature in Celsius (\u02daC). Not many devices have this sensor available.",
    field: "sensor_temperature",
    platform: "android",
    group: "android",
    icon: "Thermostat",
    settings: "SensorTemperatureSubContent",
  },
  {
    name: "Applications",
    description: "Application usage and incoming notifications on the device.",
    field: "sensor_application",
    platform: "android",
    group: "android",
    icon: "Apps",
    settings: "SensorApplicationSubContent",
  },
  {
    name: "Installations",
    description: "Application installations, removal, and updates.",
    field: "sensor_installation",
    platform: "android",
    group: "android",
    icon: "InstallMobile",
    settings: null,
  },
  {
    name: "Telephony",
    description:
      "Information on the mobile phone capabilities of the device, connected cell towers, and neighboring towers.",
    field: "sensor_telephony",
    platform: "android",
    group: "android",
    icon: "SignalCellularAlt",
    settings: null,
  },
  {
    name: "Screenshot",
    description: "Smartphone screenshot capture.",
    field: "sensor_screenshot",
    platform: "android",
    group: "android",
    icon: "ScreenshotMonitor",
    settings: "SensorScreenshotSubContent",
  },
  {
    name: "Taking Note",
    description:
      "Allow participants to take notes. Maximum length of each note is 10000 characters.",
    field: "sensor_notes",
    platform: "android",
    group: "android",
    icon: "NoteAlt",
    settings: null,
  },
  {
    name: "Activity Recognition",
    description:
      "Detect physical activity (walking, running, driving, etc.) using Google's activity recognition API",
    field: "status_plugin_google_activity_recognition",
    platform: "ios",
    group: "ios",
    icon: "DirectionsWalk",
    settings: "PluginActivityRecognitionSubContent",
  },
  {
    name: "Contacts",
    description:
      "Periodically sync the device contacts list (hashed for privacy)",
    field: "status_plugin_contacts",
    platform: "ios",
    group: "ios",
    icon: "Contacts",
    settings: "PluginContactsListSubContent",
  },
  {
    name: "Fitbit",
    description:
      "Sync Fitbit wearable data (steps, heart rate, sleep) via the Fitbit API",
    field: "status_plugin_fitbit",
    platform: "ios",
    group: "ios",
    icon: "Watch",
    settings: "PluginFitbitSubContent",
  },
  {
    name: "Google Login",
    description: "Authenticate participants with their Google account",
    field: "status_plugin_google_login",
    platform: "ios",
    group: "ios",
    icon: "AccountCircle",
    settings: null,
  },
  {
    name: "Conversation",
    description: "Detect conversational audio events without recording content",
    field: "status_plugin_studentlife_audio",
    platform: "ios",
    group: "ios",
    icon: "RecordVoiceOver",
    settings: "PluginConversationsSubContent",
  },
  {
    name: "Fused Location",
    description:
      "High-accuracy location using Google's fused location provider (GPS + network)",
    field: "status_google_fused_location",
    platform: "ios",
    group: "ios",
    icon: "MyLocation",
    settings: "PluginGoogleFusedLocationSubContent",
  },
  {
    name: "Device Usage",
    description: "Track app usage and screen-on/off events",
    field: "status_plugin_device_usage",
    platform: "ios",
    group: "ios",
    icon: "MobileFriendly",
    settings: null,
  },
  {
    name: "Calendar",
    description: "Log calendar events (title, location, dates).",
    field: "status_plugin_calendar",
    platform: "ios",
    group: "ios",
    icon: "CalendarMonth",
    settings: null,
  },
  {
    name: "Google Calendar ESM",
    description:
      "Schedule ESM questionnaires using iOS calendar events (Google Calendar ESM scheduler).",
    field: "status_ios_esm_scheduler",
    platform: "ios",
    group: "ios",
    icon: "EventNote",
    settings: null,
  },
  {
    name: "Headphone Motion",
    description:
      "Log motion sensor data from AirPods and compatible headphones.",
    field: "status_plugin_headphone_motion",
    platform: "ios",
    group: "ios",
    icon: "Headphones",
    settings: null,
  },
  {
    name: "HealthKit",
    description:
      "Sync HealthKit data (steps, sleep, heart rate, workouts, etc.).",
    field: "status_health_kit",
    platform: "ios",
    group: "ios",
    icon: "MonitorHeart",
    settings: "PluginHealthKitSubContent",
  },
  {
    name: "Heart Rate (BLE)",
    description:
      "Measure heart rate via a Bluetooth Low Energy wearable sensor.",
    field: "status_plugin_ble_heartrate",
    platform: "ios",
    group: "ios",
    icon: "FavoriteBorder",
    settings: "PluginBLEHeartRateSubContent",
  },
  {
    name: "NTP",
    description: "Sync and log the device clock offset against NTP servers.",
    field: "status_plugin_ntptime",
    platform: "ios",
    group: "ios",
    icon: "AccessTime",
    settings: null,
  },
  {
    name: "Pedometer",
    description:
      "Log step count, distance, floors climbed, and cadence via CoreMotion.",
    field: "status_plugin_ios_pedometer",
    platform: "ios",
    group: "ios",
    icon: "Hiking",
    settings: "PluginIosPedometerSubContent",
  },
  {
    name: "Push Notification",
    description: "Enable push notification delivery to study participants.",
    field: "status_push_notification",
    platform: "ios",
    group: "ios",
    icon: "NotificationsActive",
    settings: "PluginPushNotificationSubContent",
  },
  {
    name: "ESM Scheduler Plugin",
    description: "Schedule and deliver ESM questionnaires to participants",
    field: "status_plugin_esm_scheduler",
    platform: "both",
    group: "plugin",
    icon: "Quiz",
    settings: null,
  },
  {
    name: "Ambient Noise Plugin",
    description: "Ambient noise sampling plugin for smartphones",
    field: "status_plugin_ambient_noise",
    platform: "both",
    group: "plugin",
    icon: "GraphicEq",
    settings: "PluginAmbientNoiseSubContent",
  },
  {
    name: "OpenWeather Plugin",
    description: "Fetch local weather data using OpenWeather API",
    field: "status_plugin_openweather",
    platform: "both",
    group: "plugin",
    icon: "WbSunny",
    settings: "PluginOpenWeatherSubContent",
  },
];

export const GROUPS = [
  { key: "both", title: "Collected on both platforms" },
  { key: "android", title: "Android only" },
  { key: "ios", title: "iOS only" },
  { key: "plugin", title: "Plugins" },
];
