import type { SensorRecord } from "../types";

export type SensorPlatform = "shared" | "android" | "ios";

export interface SensorConfig {
  key: string;
  label: string;
  unit: string;
  color: string;
  platform: SensorPlatform;
  extract: (r: SensorRecord) => number | null;
  enumLabels?: Record<number, string>;
  countOnly?: boolean;
  note?: string;
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

export const SHARED_SENSOR_CONFIGS: SensorConfig[] = [
  {
    key: "accelerometer",
    label: "Accelerometer",
    unit: "g",
    color: "#f59e0b",
    platform: "shared",
    extract: vectorMagnitude,
  },
  {
    key: "barometer",
    label: "Barometer",
    unit: "hPa",
    color: "#64748b",
    platform: "shared",
    extract: (r) => firstNumber(r, ["pressure", "double_values_0"]),
  },
  {
    key: "battery",
    label: "Battery Level",
    unit: "%",
    color: "#22c55e",
    platform: "shared",
    extract: (r) => firstNumber(r, ["battery_level", "level", "batteryLevel"]),
    note: "iPhone battery values are approximate and are usually reported in 5% increments.",
  },
  {
    key: "battery-charges",
    label: "Battery Charges",
    unit: "event",
    color: "#16a34a",
    platform: "shared",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "battery-discharges",
    label: "Battery Discharges",
    unit: "event",
    color: "#65a30d",
    platform: "shared",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "bluetooth",
    label: "Bluetooth RSSI",
    unit: "dBm",
    color: "#06b6d4",
    platform: "shared",
    extract: (r) => firstNumber(r, ["bt_rssi", "rssi"]),
  },
  {
    key: "calls",
    label: "Calls",
    unit: "event",
    color: "#f97316",
    platform: "shared",
    extract: (r) => firstNumber(r, ["call_duration"]) ?? eventPresence(r),
  },
  {
    key: "gyroscope",
    label: "Gyroscope",
    unit: "rad/s",
    color: "#ef4444",
    platform: "shared",
    extract: vectorMagnitude,
  },
  {
    key: "linear-accelerometer",
    label: "Linear Accelerometer",
    unit: "g",
    color: "#84cc16",
    platform: "shared",
    extract: vectorMagnitude,
    note: "Movement-only acceleration with gravity removed. Values are approximate G-force units, so a still phone should be near 0 on all axes.",
  },
  {
    key: "locations",
    label: "Location Speed",
    unit: "m/s",
    color: "#10b981",
    platform: "shared",
    extract: (r) =>
      firstNumber(r, ["double_speed", "speed", "horizontal_accuracy"]),
  },
  {
    key: "magnetometer",
    label: "Magnetometer",
    unit: "uT",
    color: "#a855f7",
    platform: "shared",
    extract: vectorMagnitude,
  },
  {
    key: "network",
    label: "Network",
    unit: "event",
    color: "#0891b2",
    platform: "shared",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "rotation",
    label: "Rotation",
    unit: "rad/s",
    color: "#f43f5e",
    platform: "shared",
    extract: (r) =>
      vectorMagnitude(r) ?? magnitude(r, "roll", "pitch", "yaw"),
  },
  {
    key: "screen",
    label: "Screen Status",
    unit: "",
    color: "#3b82f6",
    platform: "shared",
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
    platform: "shared",
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
    platform: "shared",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "wifi",
    label: "WiFi",
    unit: "",
    color: "#8b5cf6",
    platform: "shared",
    extract: (r) => firstNumber(r, ["rssi", "wifi_rssi"]),
  },
];

export const ANDROID_SENSOR_CONFIGS: SensorConfig[] = [
  {
    key: "applications",
    label: "Applications",
    unit: "event",
    color: "#9333ea",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-crashes",
    label: "Application Crashes",
    unit: "event",
    color: "#dc2626",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-history",
    label: "Application History",
    unit: "event",
    color: "#7c3aed",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "applications-notifications",
    label: "Application Notifications",
    unit: "event",
    color: "#a855f7",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "esms",
    label: "ESM/EMA",
    unit: "event",
    color: "#7c2d12",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "gravity",
    label: "Gravity",
    unit: "g",
    color: "#84cc16",
    platform: "android",
    extract: vectorMagnitude,
  },
  {
    key: "installations",
    label: "Installations",
    unit: "event",
    color: "#0284c7",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "keyboard",
    label: "Keyboard",
    unit: "event",
    color: "#334155",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "light",
    label: "Light",
    unit: "lux",
    color: "#fbbf24",
    platform: "android",
    extract: (r) => firstNumber(r, ["double_light_lux", "light_lux", "value"]),
  },
  {
    key: "messages",
    label: "Messages",
    unit: "event",
    color: "#fb923c",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "network-traffic",
    label: "Network Traffic",
    unit: "bytes",
    color: "#0e7490",
    platform: "android",
    extract: (r) =>
      firstNumber(r, ["tx_bytes", "rx_bytes", "double_tx", "double_rx"]) ??
      eventPresence(r),
  },
  {
    key: "notes",
    label: "Notes",
    unit: "event",
    color: "#ca8a04",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "plugin-ambient-noise",
    label: "Ambient Noise",
    unit: "",
    color: "#0ea5e9",
    platform: "android",
    extract: (r) =>
      firstNumber(r, ["double_decibels", "decibels", "is_silent", "silent"]) ??
      eventPresence(r),
  },
  {
    key: "plugin-openweather",
    label: "OpenWeather",
    unit: "degC",
    color: "#ca8a04",
    platform: "android",
    extract: (r) => firstNumber(r, ["temperature", "temp", "value"]) ?? eventPresence(r),
  },
  {
    key: "proximity",
    label: "Proximity",
    unit: "",
    color: "#0f766e",
    platform: "android",
    extract: (r) => firstNumber(r, ["distance", "near", "value"]) ?? eventPresence(r),
  },
  {
    key: "screentext",
    label: "Screen Text",
    unit: "event",
    color: "#1d4ed8",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "telephony",
    label: "Telephony",
    unit: "event",
    color: "#0f766e",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "temperature",
    label: "Temperature",
    unit: "degC",
    color: "#ea580c",
    platform: "android",
    extract: (r) => firstNumber(r, ["double_temperature", "temperature", "value"]),
  },
  {
    key: "touch",
    label: "Touch",
    unit: "event",
    color: "#475569",
    platform: "android",
    extract: eventPresence,
    countOnly: true,
  },
];

export const IOS_SENSOR_CONFIGS: SensorConfig[] = [
  {
    key: "activity",
    label: "Activity Recognition",
    unit: "event",
    color: "#2563eb",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "ambient-noise",
    label: "Ambient Noise",
    unit: "",
    color: "#0ea5e9",
    platform: "ios",
    extract: (r) => firstNumber(r, ["is_silent", "silent"]),
    enumLabels: {
      0: "Noisy",
      1: "Silent",
    },
  },
  {
    key: "ble-heartrate",
    label: "Heart Rate (BLE)",
    unit: "bpm",
    color: "#dc2626",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["heart_rate", "heartrate", "bpm", "value"]) ??
      eventPresence(r),
  },
  {
    key: "calendar",
    label: "Calendar",
    unit: "event",
    color: "#0284c7",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "calendar-esm-scheduler",
    label: "Google Calendar ESM",
    unit: "event",
    color: "#0369a1",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "contacts",
    label: "Contacts",
    unit: "event",
    color: "#0891b2",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "device-usage",
    label: "Device Usage",
    unit: "event",
    color: "#9333ea",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "esm",
    label: "Mobile ESM/EMA",
    unit: "event",
    color: "#7c2d12",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "esm-scheduler",
    label: "ESM Scheduler",
    unit: "event",
    color: "#9a3412",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fitbit",
    label: "Fitbit",
    unit: "event",
    color: "#0d9488",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fitbit-data",
    label: "Fitbit Data",
    unit: "",
    color: "#0f766e",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["value", "steps", "heart_rate"]) ?? eventPresence(r),
  },
  {
    key: "fitbit-device",
    label: "Fitbit Device",
    unit: "event",
    color: "#115e59",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "fused-location",
    label: "Fused Location",
    unit: "m",
    color: "#16a34a",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["accuracy", "horizontal_accuracy", "speed"]) ??
      eventPresence(r),
  },
  {
    key: "headphone-motion",
    label: "Headphone Motion",
    unit: "m/s^2",
    color: "#db2777",
    platform: "ios",
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
    platform: "ios",
    extract: (r) => firstNumber(r, ["value", "quantity"]) ?? eventPresence(r),
  },
  {
    key: "health-kit/category",
    label: "HealthKit Category",
    unit: "event",
    color: "#fb7185",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "health-kit/quantity",
    label: "HealthKit Quantity",
    unit: "",
    color: "#be123c",
    platform: "ios",
    extract: (r) => firstNumber(r, ["quantity", "value"]) ?? eventPresence(r),
  },
  {
    key: "health-kit/workout",
    label: "HealthKit Workout",
    unit: "event",
    color: "#9f1239",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["duration", "distance", "energy"]) ?? eventPresence(r),
  },
  {
    key: "location-visit",
    label: "Location Visit",
    unit: "event",
    color: "#15803d",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "memory",
    label: "Memory",
    unit: "",
    color: "#475569",
    platform: "ios",
    extract: (r) => firstNumber(r, ["used", "free", "total", "value"]) ?? eventPresence(r),
  },
  {
    key: "ntptime",
    label: "NTP",
    unit: "ms",
    color: "#4f46e5",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["offset", "delay", "latency", "value"]) ??
      eventPresence(r),
  },
  {
    key: "openweather",
    label: "OpenWeather",
    unit: "degC",
    color: "#ca8a04",
    platform: "ios",
    extract: (r) => firstNumber(r, ["temperature", "temp", "value"]) ?? eventPresence(r),
  },
  {
    key: "pedometer",
    label: "Pedometer",
    unit: "steps",
    color: "#ec4899",
    platform: "ios",
    extract: (r) =>
      firstNumber(r, ["step_count", "steps", "number_of_steps", "distance"]) ??
      eventPresence(r),
  },
  {
    key: "processor",
    label: "Processor",
    unit: "%",
    color: "#475569",
    platform: "shared",
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
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
  {
    key: "studentlife-audio",
    label: "Conversation",
    unit: "event",
    color: "#7c3aed",
    platform: "ios",
    extract: eventPresence,
    countOnly: true,
  },
];

export const SENSOR_CONFIGS: SensorConfig[] = [
  ...SHARED_SENSOR_CONFIGS,
  ...ANDROID_SENSOR_CONFIGS,
  ...IOS_SENSOR_CONFIGS,
];

export function sensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  return SENSOR_CONFIGS.filter(
    (s) => s.platform === "shared" || s.platform === platform,
  );
}

export function deviceSensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  return sensorsForPlatform(platform);
}
