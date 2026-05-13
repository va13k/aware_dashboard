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

export const SENSOR_CONFIGS: SensorConfig[] = [
  // ── Shared ──────────────────────────────────────────────────────────────
  {
    key: "battery",
    label: "Battery Level",
    unit: "%",
    color: "#22c55e",
    platform: "shared",
    // Android: battery_level column; iOS JSON: level
    extract: (r) =>
      (r.battery_level as number | null) ?? (r.level as number | null) ?? null,
    note: "iPhone battery values are approximate and are usually reported in 5% increments.",
  },
  {
    key: "screen",
    label: "Screen Status",
    unit: "",
    color: "#3b82f6",
    platform: "shared",
    // Android: screen_status column; iOS JSON: status
    extract: (r) =>
      (r.screen_status as number | null) ?? (r.status as number | null) ?? null,
    enumLabels: {
      0: "Screen off",
      1: "Screen on",
      2: "Screen locked",
      3: "Screen unlocked",
    },
    note: "Received values can differ across iOS and iPhone versions.",
  },
  {
    key: "accelerometer",
    label: "Accelerometer",
    unit: "g",
    color: "#f59e0b",
    platform: "shared",
    // Android: double_values_0/1/2 columns; iOS JSON: x/y/z
    extract: (r) =>
      magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
      magnitude(r, "x", "y", "z"),
  },
  {
    key: "gyroscope",
    label: "Gyroscope",
    unit: "rad/s",
    color: "#ef4444",
    platform: "shared",
    // Android: double_values_0/1/2 columns; iOS JSON: x/y/z
    extract: (r) =>
      magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
      magnitude(r, "x", "y", "z"),
  },
  {
    key: "locations",
    label: "GPS Speed",
    unit: "m/s",
    color: "#10b981",
    platform: "shared",
    // Android: double_speed column; iOS JSON: speed
    extract: (r) =>
      (r.double_speed as number | null) ?? (r.speed as number | null) ?? null,
  },
  {
    key: "wifi",
    label: "WiFi",
    unit: "",
    color: "#8b5cf6",
    platform: "shared",
    // Used only for fallback stat/chart paths; Wi-Fi rows render in WifiRecordsCard.
    extract: (r) => (r.rssi as number | null) ?? null,
  },
  {
    key: "bluetooth",
    label: "Bluetooth RSSI",
    unit: "dBm",
    color: "#06b6d4",
    platform: "shared",
    // Android: bt_rssi column; iOS JSON: rssi
    extract: (r) =>
      (r.bt_rssi as number | null) ?? (r.rssi as number | null) ?? null,
  },
  {
    key: "calls",
    label: "Call Duration",
    unit: "s",
    color: "#f97316",
    platform: "shared",
    // Android: call_duration column; iOS JSON: call_duration
    extract: (r) => (r.call_duration as number | null) ?? null,
  },

  // ── Android only ─────────────────────────────────────────────────────────
  {
    key: "light",
    label: "Light",
    unit: "lux",
    color: "#fbbf24",
    platform: "android",
    // Android: double_light_lux column
    extract: (r) => (r.double_light_lux as number | null) ?? null,
  },

  // ── iOS only ─────────────────────────────────────────────────────────────
  {
    key: "barometer",
    label: "Barometer",
    unit: "hPa",
    color: "#64748b",
    platform: "ios",
    // iOS JSON: pressure (kPa from CoreMotion, displayed as hPa)
    extract: (r) => (r.pressure as number | null) ?? null,
  },
  {
    key: "magnetometer",
    label: "Magnetometer",
    unit: "µT",
    color: "#a855f7",
    platform: "ios",
    // iOS JSON: x/y/z (µT from CoreMotion CMMagneticField)
    extract: (r) => magnitude(r, "x", "y", "z"),
  },
  {
    key: "rotation",
    label: "Rotation",
    unit: "rad/s",
    color: "#f43f5e",
    platform: "ios",
    // iOS JSON: x/y/z (CMRotationRate) or roll/pitch/yaw (CMAttitude)
    extract: (r) =>
      magnitude(r, "x", "y", "z") ?? magnitude(r, "roll", "pitch", "yaw"),
  },
  {
    key: "ambient-noise",
    label: "Ambient Noise",
    unit: "",
    color: "#0ea5e9",
    platform: "ios",
    // iOS JSON: is_silent uses 0 = noisy, 1 = silent.
    extract: (r) => firstNumber(r, ["is_silent", "silent"]),
    enumLabels: {
      0: "Noisy",
      1: "Silent",
    },
  },
  {
    key: "health-kit",
    label: "HealthKit",
    unit: "",
    color: "#e11d48",
    platform: "ios",
    // iOS JSON: value (generic health_kit quantity)
    extract: (r) => (r.value as number | null) ?? null,
  },
  {
    key: "health-kit/quantity",
    label: "HealthKit Quantity",
    unit: "",
    color: "#be123c",
    platform: "ios",
    // iOS JSON: quantity or value (health_kit_quantity table)
    extract: (r) =>
      (r.quantity as number | null) ?? (r.value as number | null) ?? null,
  },
  {
    key: "pedometer",
    label: "Step Count",
    unit: "steps",
    color: "#ec4899",
    platform: "ios",
    // iOS JSON: step_count (plugin_ios_pedometer table)
    extract: (r) =>
      (r.step_count as number | null) ?? (r.steps as number | null) ?? null,
  },
];

export function sensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  return SENSOR_CONFIGS.filter(
    (s) => s.platform === "shared" || s.platform === platform,
  );
}

const IOS_DEVICE_SENSOR_CONFIGS: SensorConfig[] = [
  // Shared sensors as exposed in the configurator for iPhone studies.
  {
    key: "battery",
    label: "Battery Level",
    unit: "%",
    color: "#22c55e",
    platform: "shared",
    extract: (r) =>
      firstNumber(r, ["battery_level", "level", "batteryLevel"]),
    note: "iPhone battery values are approximate and are usually reported in 5% increments.",
  },
  {
    key: "calls",
    label: "Calls",
    unit: "event",
    color: "#f97316",
    platform: "shared",
    extract: eventPresence,
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
    key: "timezone",
    label: "Timezone",
    unit: "event",
    color: "#14b8a6",
    platform: "shared",
    extract: eventPresence,
  },
  {
    key: "accelerometer",
    label: "Accelerometer",
    unit: "g",
    color: "#f59e0b",
    platform: "shared",
    extract: (r) =>
      magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
      magnitude(r, "x", "y", "z"),
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
    key: "bluetooth",
    label: "Bluetooth RSSI",
    unit: "dBm",
    color: "#06b6d4",
    platform: "shared",
    extract: (r) => firstNumber(r, ["bt_rssi", "rssi"]),
  },
  {
    key: "gyroscope",
    label: "Gyroscope",
    unit: "rad/s",
    color: "#ef4444",
    platform: "shared",
    extract: (r) =>
      magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
      magnitude(r, "x", "y", "z"),
  },
  {
    key: "linear-accelerometer",
    label: "Linear Accelerometer",
    unit: "g",
    color: "#84cc16",
    platform: "shared",
    extract: (r) =>
      magnitude(r, "double_values_0", "double_values_1", "double_values_2") ??
      magnitude(r, "x", "y", "z"),
    note: "Movement-only acceleration with gravity removed. Values are approximate G-force units, so a still phone should be near 0 on all axes.",
  },
  {
    key: "locations",
    label: "Location Speed",
    unit: "m/s",
    color: "#10b981",
    platform: "shared",
    extract: (r) => firstNumber(r, ["double_speed", "speed", "horizontal_accuracy"]),
  },
  {
    key: "magnetometer",
    label: "Magnetometer",
    unit: "µT",
    color: "#a855f7",
    platform: "shared",
    extract: (r) => magnitude(r, "x", "y", "z"),
  },
  {
    key: "processor",
    label: "Processor",
    unit: "%",
    color: "#475569",
    platform: "shared",
    extract: (r) => firstNumber(r, ["load", "processor_load", "usage", "value"]),
  },
  {
    key: "rotation",
    label: "Rotation",
    unit: "rad/s",
    color: "#f43f5e",
    platform: "shared",
    extract: (r) =>
      magnitude(r, "x", "y", "z") ?? magnitude(r, "roll", "pitch", "yaw"),
  },
  {
    key: "proximity",
    label: "Proximity",
    unit: "",
    color: "#0f766e",
    platform: "shared",
    extract: (r) => firstNumber(r, ["distance", "near", "value"]) ?? eventPresence(r),
  },
  {
    key: "significant-motion",
    label: "Significant Motion",
    unit: "event",
    color: "#2563eb",
    platform: "shared",
    extract: eventPresence,
  },
  {
    key: "wifi",
    label: "WiFi",
    unit: "",
    color: "#8b5cf6",
    platform: "shared",
    extract: (r) => firstNumber(r, ["rssi", "wifi_rssi"]),
  },

  // iOS-only sensors and plugins as exposed in SensorData.jsx.
  {
    key: "contacts",
    label: "Contacts",
    unit: "event",
    color: "#0891b2",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "fitbit",
    label: "Fitbit",
    unit: "event",
    color: "#0d9488",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "fitbit-data",
    label: "Fitbit Data",
    unit: "",
    color: "#0f766e",
    platform: "ios",
    extract: (r) => firstNumber(r, ["value", "steps", "heart_rate"]) ?? eventPresence(r),
  },
  {
    key: "fitbit-device",
    label: "Fitbit Device",
    unit: "event",
    color: "#115e59",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "studentlife-audio",
    label: "Conversation",
    unit: "event",
    color: "#7c3aed",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "fused-location",
    label: "Fused Location",
    unit: "m",
    color: "#16a34a",
    platform: "ios",
    extract: (r) => firstNumber(r, ["accuracy", "horizontal_accuracy", "speed"]) ?? eventPresence(r),
  },
  {
    key: "device-usage",
    label: "Device Usage",
    unit: "event",
    color: "#9333ea",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "calendar",
    label: "Calendar",
    unit: "event",
    color: "#0284c7",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "calendar-esm-scheduler",
    label: "Google Calendar ESM",
    unit: "event",
    color: "#0369a1",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "headphone-motion",
    label: "Headphone Motion",
    unit: "m/s²",
    color: "#db2777",
    platform: "ios",
    extract: (r) =>
      magnitude(r, "x", "y", "z") ??
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
    extract: (r) => firstNumber(r, ["duration", "distance", "energy"]) ?? eventPresence(r),
  },
  {
    key: "ble-heartrate",
    label: "Heart Rate (BLE)",
    unit: "bpm",
    color: "#dc2626",
    platform: "ios",
    extract: (r) => firstNumber(r, ["heart_rate", "heartrate", "bpm", "value"]) ?? eventPresence(r),
  },
  {
    key: "ntptime",
    label: "NTP",
    unit: "ms",
    color: "#4f46e5",
    platform: "ios",
    extract: (r) => firstNumber(r, ["offset", "delay", "latency", "value"]) ?? eventPresence(r),
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
    key: "push-notification",
    label: "Push Notification",
    unit: "",
    color: "#ea580c",
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
    key: "openweather",
    label: "OpenWeather",
    unit: "°C",
    color: "#ca8a04",
    platform: "ios",
    extract: (r) => firstNumber(r, ["temperature", "temp", "value"]) ?? eventPresence(r),
  },
  {
    key: "esm",
    label: "Mobile ESM/EMA",
    unit: "event",
    color: "#7c2d12",
    platform: "ios",
    extract: eventPresence,
  },
  {
    key: "esm-scheduler",
    label: "ESM Scheduler",
    unit: "event",
    color: "#9a3412",
    platform: "ios",
    extract: eventPresence,
  },
];

export function deviceSensorsForPlatform(
  platform: "android" | "ios",
): SensorConfig[] {
  if (platform === "ios") return IOS_DEVICE_SENSOR_CONFIGS;
  return sensorsForPlatform(platform);
}
