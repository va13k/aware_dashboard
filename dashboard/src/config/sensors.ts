import type { SensorRecord } from "../types";

export type SensorPlatform = "shared" | "android" | "ios";

/** The table serving a sensor on each platform it is collected on.
 *
 * The same capability is often stored under different names — an ESM answer is
 * `esms` on Android and `plugin_ios_esm` on an iPhone — so naming the table per
 * platform is what lets one card cover both. A side left out is a platform that
 * does not collect it.
 */
export interface SensorTables {
  android?: string;
  ios?: string;
}

export interface SensorConfig {
  key: string;
  label: string;
  unit: string;
  color: string;
  tables: SensorTables;
  extract: (r: SensorRecord) => number | null;
  enumLabels?: Record<number, string>;
  countOnly?: boolean;
  note?: string;
}

/** Which platforms collect a sensor, read from the tables that serve it. */
export function sensorPlatform(sensor: SensorConfig): SensorPlatform {
  const onAndroid = sensor.tables.android != null;
  const onIos = sensor.tables.ios != null;
  if (onAndroid && onIos) return "shared";
  return onAndroid ? "android" : "ios";
}

function magnitude(
  r: SensorRecord,
  ax: string,
  ay: string,
  az: string,
): number | null {
  const x = numberValue(r[ax]);
  const y = numberValue(r[ay]);
  const z = numberValue(r[az]);
  if (x == null || y == null || z == null) return null;
  return Math.sqrt(x * x + y * y + z * z);
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function firstNumber(r: SensorRecord, keys: string[]): number | null {
  for (const key of keys) {
    const value = numberValue(r[key]);
    if (value != null) return value;
  }
  return null;
}

function eventPresence(r: SensorRecord): number | null {
  return r.timestamp == null ? null : 1;
}

function motionState(r: SensorRecord): number | null {
  const value = r.is_moving;
  if (typeof value === "boolean") return value ? 1 : 0;
  return firstNumber(r, ["is_moving"]);
}

const vectorMagnitude = (r: SensorRecord) =>
  magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
  magnitude(r, "x", "y", "z");

const ALL_SENSOR_CONFIGS: SensorConfig[] = [
  {
    key: "accelerometer",
    label: "Accelerometer",
    unit: "g",
    color: "#f59e0b",
    tables: { android: "accelerometer", ios: "accelerometer" },
    extract: vectorMagnitude,
  },
  {
    key: "barometer",
    label: "Barometer",
    unit: "hPa",
    color: "#64748b",
    tables: { android: "barometer", ios: "barometer" },
    extract: (r) => firstNumber(r, ["pressure", "double_values_0"]),
  },
  {
    key: "battery",
    label: "Battery Level",
    unit: "%",
    color: "#22c55e",
    tables: { android: "battery", ios: "battery" },
    extract: (r) => firstNumber(r, ["battery_level", "level", "batteryLevel"]),
    note: "iPhone battery values are approximate and are usually reported in 5% increments.",
  },
  {
    key: "battery-charges",
    label: "Battery Charges",
    unit: "event",
    color: "#16a34a",
    tables: { android: "battery_charges", ios: "battery_charges" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "battery-discharges",
    label: "Battery Discharges",
    unit: "event",
    color: "#65a30d",
    tables: { android: "battery_discharges", ios: "battery_discharges" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "bluetooth",
    label: "Bluetooth RSSI",
    unit: "dBm",
    color: "#06b6d4",
    tables: { android: "bluetooth", ios: "bluetooth" },
    extract: (r) => firstNumber(r, ["bt_rssi", "rssi"]),
  },
  {
    key: "calls",
    label: "Calls",
    unit: "event",
    color: "#f97316",
    tables: { android: "calls", ios: "calls" },
    extract: (r) => firstNumber(r, ["call_duration"]) ?? eventPresence(r),
  },
  {
    key: "gyroscope",
    label: "Gyroscope",
    unit: "rad/s",
    color: "#ef4444",
    tables: { android: "gyroscope", ios: "gyroscope" },
    extract: vectorMagnitude,
  },
  {
    key: "linear-accelerometer",
    label: "Linear Accelerometer",
    unit: "g",
    color: "#84cc16",
    tables: { android: "linear_accelerometer", ios: "linear_accelerometer" },
    extract: vectorMagnitude,
    note: "Movement-only acceleration with gravity removed. Values are approximate G-force units, so a still phone should be near 0 on all axes.",
  },
  {
    key: "locations",
    label: "Location Speed",
    unit: "m/s",
    color: "#10b981",
    tables: { android: "locations", ios: "locations" },
    extract: (r) =>
      firstNumber(r, ["double_speed", "speed", "horizontal_accuracy"]),
  },
  {
    key: "magnetometer",
    label: "Magnetometer",
    unit: "uT",
    color: "#a855f7",
    tables: { android: "magnetometer", ios: "magnetometer" },
    extract: vectorMagnitude,
  },
  {
    key: "network",
    label: "Network",
    unit: "event",
    color: "#0891b2",
    tables: { android: "network", ios: "network" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "rotation",
    label: "Rotation",
    unit: "rad/s",
    color: "#f43f5e",
    tables: { android: "rotation", ios: "rotation" },
    extract: (r) => vectorMagnitude(r) ?? magnitude(r, "roll", "pitch", "yaw"),
  },
  {
    key: "screen",
    label: "Screen Status",
    unit: "",
    color: "#3b82f6",
    tables: { android: "screen", ios: "screen" },
    extract: (r) => firstNumber(r, ["screen_status", "status"]),
    enumLabels: {
      0: "Screen off",
      1: "Screen on",
      2: "Screen locked",
      3: "Screen unlocked",
    },
    note: "Received values can differ across iOS and iPhone versions.",
  },
  {
    key: "significant-motion",
    label: "Significant Motion",
    unit: "",
    color: "#2563eb",
    tables: { android: "significant", ios: "significant_motion" },
    extract: motionState,
    enumLabels: {
      0: "Not moving",
      1: "Moving",
    },
    note: "The chart marks state changes: moving starts at 1 and ends at 0.",
  },
  {
    key: "timezone",
    label: "Timezone",
    unit: "event",
    color: "#14b8a6",
    tables: { android: "timezone", ios: "timezone" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "wifi",
    label: "WiFi",
    unit: "",
    color: "#8b5cf6",
    tables: { android: "wifi", ios: "sensor_wifi" },
    extract: (r) => firstNumber(r, ["rssi", "wifi_rssi"]),
  },
  {
    key: "applications",
    label: "Applications",
    unit: "event",
    color: "#9333ea",
    tables: { android: "applications_foreground" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-crashes",
    label: "Application Crashes",
    unit: "event",
    color: "#dc2626",
    tables: { android: "applications_crashes" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-history",
    label: "Application History",
    unit: "event",
    color: "#7c3aed",
    tables: { android: "applications_history" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-notifications",
    label: "Application Notifications",
    unit: "event",
    color: "#a855f7",
    tables: { android: "applications_notifications" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "gravity",
    label: "Gravity",
    unit: "g",
    color: "#84cc16",
    tables: { android: "gravity" },
    extract: vectorMagnitude,
  },
  {
    key: "installations",
    label: "Installations",
    unit: "event",
    color: "#0284c7",
    tables: { android: "installations" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "keyboard",
    label: "Keyboard",
    unit: "event",
    color: "#334155",
    tables: { android: "keyboard" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "light",
    label: "Light",
    unit: "lux",
    color: "#fbbf24",
    tables: { android: "light" },
    extract: (r) => firstNumber(r, ["double_light_lux", "light_lux", "value"]),
  },
  {
    key: "messages",
    label: "Messages",
    unit: "event",
    color: "#fb923c",
    tables: { android: "messages" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "network-traffic",
    label: "Network Traffic",
    unit: "bytes",
    color: "#0e7490",
    tables: { android: "network_traffic" },
    extract: (r) =>
      firstNumber(r, ["tx_bytes", "rx_bytes", "double_tx", "double_rx"]) ??
      eventPresence(r),
  },
  {
    key: "notes",
    label: "Notes",
    unit: "event",
    color: "#ca8a04",
    tables: { android: "notes" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "plugin-ambient-noise",
    label: "Ambient Noise",
    unit: "dB",
    color: "#0ea5e9",
    tables: { android: "plugin_ambient_noise", ios: "plugin_ambient_noise" },
    extract: (r) => firstNumber(r, ["double_decibels", "decibels"]),
  },
  {
    key: "proximity",
    label: "Proximity",
    unit: "",
    color: "#0f766e",
    tables: { android: "proximity" },
    extract: (r) =>
      firstNumber(r, ["distance", "near", "value"]) ?? eventPresence(r),
  },
  {
    key: "screentext",
    label: "Screen Text",
    unit: "event",
    color: "#1d4ed8",
    tables: { android: "screentext" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "telephony",
    label: "Telephony",
    unit: "event",
    color: "#0f766e",
    tables: { android: "telephony" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "temperature",
    label: "Temperature",
    unit: "degC",
    color: "#ea580c",
    tables: { android: "temperature" },
    extract: (r) =>
      firstNumber(r, ["double_temperature", "temperature", "value"]),
  },
  {
    key: "touch",
    label: "Touch",
    unit: "event",
    color: "#475569",
    tables: { android: "touch" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "activity",
    label: "Activity Recognition",
    unit: "event",
    color: "#2563eb",
    tables: { ios: "plugin_ios_activity_recognition" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "ble-heartrate",
    label: "Heart Rate (BLE)",
    unit: "bpm",
    color: "#dc2626",
    tables: { ios: "plugin_ble_heartrate" },
    extract: (r) =>
      firstNumber(r, ["heart_rate", "heartrate", "bpm", "value"]) ??
      eventPresence(r),
  },
  {
    key: "calendar",
    label: "Calendar",
    unit: "event",
    color: "#0284c7",
    tables: { ios: "plugin_calendar" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "contacts",
    label: "Contacts",
    unit: "event",
    color: "#0891b2",
    tables: { ios: "plugin_contacts" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "device-usage",
    label: "Device Usage",
    unit: "event",
    color: "#9333ea",
    tables: { ios: "plugin_device_usage" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "esm",
    label: "Mobile ESM/EMA",
    unit: "event",
    color: "#7c2d12",
    tables: { android: "esms", ios: "plugin_ios_esm" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "esm-scheduler",
    label: "ESM Scheduler",
    unit: "event",
    color: "#9a3412",
    tables: { android: "scheduler", ios: "plugin_calendar_esm_scheduler" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fitbit",
    label: "Fitbit",
    unit: "event",
    color: "#0d9488",
    tables: { ios: "plugin_fitbit" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fitbit-data",
    label: "Fitbit Data",
    unit: "",
    color: "#0f766e",
    tables: { ios: "fitbit_data" },
    extract: (r) =>
      firstNumber(r, ["value", "steps", "heart_rate"]) ?? eventPresence(r),
  },
  {
    key: "fitbit-device",
    label: "Fitbit Device",
    unit: "event",
    color: "#115e59",
    tables: { ios: "fitbit_device" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fused-location",
    label: "Fused Location",
    unit: "m",
    color: "#16a34a",
    tables: { ios: "google_fused_location" },
    extract: (r) =>
      firstNumber(r, ["accuracy", "horizontal_accuracy", "speed"]) ??
      eventPresence(r),
  },
  {
    key: "headphone-motion",
    label: "Headphone Motion",
    unit: "m/s^2",
    color: "#db2777",
    tables: { ios: "plugin_headphone_motion" },
    extract: (r) =>
      vectorMagnitude(r) ??
      magnitude(r, "acceleration_x", "acceleration_y", "acceleration_z") ??
      eventPresence(r),
  },
  {
    key: "health-kit",
    label: "HealthKit",
    unit: "",
    color: "#e11d48",
    tables: { ios: "health_kit" },
    extract: (r) => firstNumber(r, ["value", "quantity"]) ?? eventPresence(r),
  },
  {
    key: "health-kit/category",
    label: "HealthKit Category",
    unit: "event",
    color: "#fb7185",
    tables: { ios: "health_kit_category" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "health-kit/quantity",
    label: "HealthKit Quantity",
    unit: "",
    color: "#be123c",
    tables: { ios: "health_kit_quantity" },
    extract: (r) => firstNumber(r, ["quantity", "value"]) ?? eventPresence(r),
  },
  {
    key: "health-kit/workout",
    label: "HealthKit Workout",
    unit: "event",
    color: "#9f1239",
    tables: { ios: "health_kit_workout" },
    extract: (r) =>
      firstNumber(r, ["duration", "distance", "energy"]) ?? eventPresence(r),
  },
  {
    key: "location-visit",
    label: "Location Visit",
    unit: "event",
    color: "#15803d",
    tables: { ios: "ios_location_visit" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "ntptime",
    label: "NTP",
    unit: "ms",
    color: "#4f46e5",
    tables: { ios: "plugin_ntptime" },
    extract: (r) =>
      firstNumber(r, ["offset", "delay", "latency", "value"]) ??
      eventPresence(r),
  },
  {
    key: "openweather",
    label: "OpenWeather",
    unit: "degC",
    color: "#ca8a04",
    tables: { android: "plugin_openweather", ios: "plugin_openweather" },
    extract: (r) =>
      firstNumber(r, ["temperature", "temp", "value"]) ?? eventPresence(r),
  },
  {
    key: "pedometer",
    label: "Pedometer",
    unit: "steps",
    color: "#ec4899",
    tables: { ios: "plugin_ios_pedometer" },
    extract: (r) =>
      firstNumber(r, ["step_count", "steps", "number_of_steps", "distance"]) ??
      eventPresence(r),
  },
  {
    key: "processor",
    label: "Processor",
    unit: "%",
    color: "#475569",
    tables: { android: "processor", ios: "processor" },
    extract: (r) =>
      firstNumber(r, [
        "double_last_user",
        "double_user_load",
        "double_last_system",
        "double_system_load",
        "load",
        "processor_load",
        "usage",
        "value",
      ]),
  },
  {
    key: "push-notification",
    label: "Push Notification",
    unit: "event",
    color: "#ea580c",
    tables: { ios: "push_notification" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "studentlife-audio",
    label: "Conversation",
    unit: "event",
    color: "#7c3aed",
    tables: { ios: "plugin_studentlife_audio" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "study-events",
    label: "Study Events",
    unit: "event",
    color: "#0f766e",
    tables: { android: "aware_studies" },
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "screenshot",
    label: "Screenshots",
    unit: "event",
    color: "#475569",
    tables: { android: "screenshot" },
    extract: eventPresence,
    countOnly: true,
    note: "Counts captures only. The images themselves stay in the database and are never read into a response.",
  },

];

export const SENSOR_CONFIGS: SensorConfig[] = ALL_SENSOR_CONFIGS;

/** The sensors both platforms collect. */
export const SHARED_SENSOR_CONFIGS: SensorConfig[] = ALL_SENSOR_CONFIGS.filter(
  (s) => sensorPlatform(s) === "shared",
);

/** The sensors only an Android phone collects. */
export const ANDROID_SENSOR_CONFIGS: SensorConfig[] = ALL_SENSOR_CONFIGS.filter(
  (s) => sensorPlatform(s) === "android",
);

/** The sensors only an iPhone collects. */
export const IOS_SENSOR_CONFIGS: SensorConfig[] = ALL_SENSOR_CONFIGS.filter(
  (s) => sensorPlatform(s) === "ios",
);

export function sensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  return SENSOR_CONFIGS.filter((s) => s.tables[platform] != null);
}

export function deviceSensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  return sensorsForPlatform(platform);
}

/**
 * Sensors the backend can aggregate into a bucketed numeric series. Currently
 * Android only: iOS stores values in an opaque JSON blob whose keys aren't
 * asserted in the repo, so its series is deferred and iOS keeps the raw view.
 * Must stay in sync with `_SERIES_TARGETS` in `routers/android.py`.
 */
export const ANDROID_SERIES_KEYS = new Set<string>([
  "accelerometer",
  "gyroscope",
  "linear-accelerometer",
  "magnetometer",
  "gravity",
  "rotation",
  "barometer",
  "light",
  "temperature",
  "plugin-ambient-noise",
  "network-traffic",
]);

/** Whether this sensor should be plotted from a server-bucketed series. */
export function sensorHasSeries(
  platform: "android" | "ios",
  key: string,
): boolean {
  return platform === "android" && ANDROID_SERIES_KEYS.has(key);
}

/**
 * Event/tabular sensors that open the logs view: their meaning lives in the
 * individual rows (enum states, scan lists, call/text events), which a paged
 * table shows directly. `countOnly` sensors resolve to logs via
 * `sensorViewType`; this set adds the row-valued sensors the plan names
 * ("wifi/bluetooth/calls") and the enum-state sensors (screen, motion).
 */
export const LOG_SENSOR_KEYS = new Set<string>([
  "wifi",
  "sensor_wifi",
  "bluetooth",
  "calls",
  "screen",
  "significant-motion",
]);

/** How a sensor is presented on demand: a chart ("plot") or a raw table ("log"). */
export type SensorViewType = "plot" | "log";

/**
 * The single source of truth for the plot-vs-log split. Steps that open a
 * sensor on demand (tile → modal) use this to choose the plot modal (numeric,
 * charted) or the logs modal (raw rows + CSV). Within the plot modal,
 * `sensorHasSeries` further decides a bucketed series vs the raw-record card.
 */
export function sensorViewType(config: SensorConfig): SensorViewType {
  if (config.countOnly) return "log";
  return LOG_SENSOR_KEYS.has(config.key) ? "log" : "plot";
}

/** A sensor's already-fetched records, keyed by the data key they belong to. */
export type SensorData = Record<string, SensorRecord[]>;

/** The data keys a sensor needs fetched (composite cards pull several). */
export function sensorDataKeys(key: string): string[] {
  if (key === "battery") {
    return ["battery", "battery-charges", "battery-discharges"];
  }
  if (key === "applications") {
    return [
      "applications",
      "applications-crashes",
      "applications-history",
      "applications-notifications",
    ];
  }
  return [key];
}
