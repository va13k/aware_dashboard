import type { SensorRecord } from '../types'

export type SensorPlatform = 'shared' | 'android' | 'ios'

export interface SensorConfig {
  key: string
  label: string
  unit: string
  color: string
  platform: SensorPlatform
  extract: (r: SensorRecord) => number | null
}

function magnitude(r: SensorRecord, ax: string, ay: string, az: string): number | null {
  const x = r[ax] as number | null
  const y = r[ay] as number | null
  const z = r[az] as number | null
  if (x == null || y == null || z == null) return null
  return Math.sqrt(x * x + y * y + z * z)
}

export const SENSOR_CONFIGS: SensorConfig[] = [
  // ── Shared ──────────────────────────────────────────────────────────────
  {
    key: 'battery',
    label: 'Battery Level',
    unit: '%',
    color: '#22c55e',
    platform: 'shared',
    // Android: battery_level column; iOS JSON: level
    extract: r => (r.battery_level as number | null) ?? (r.level as number | null) ?? null,
  },
  {
    key: 'screen',
    label: 'Screen Status',
    unit: '',
    color: '#3b82f6',
    platform: 'shared',
    // Android: screen_status column; iOS JSON: status
    extract: r => (r.screen_status as number | null) ?? (r.status as number | null) ?? null,
  },
  {
    key: 'accelerometer',
    label: 'Accelerometer',
    unit: 'm/s²',
    color: '#f59e0b',
    platform: 'shared',
    // Android: double_values_0/1/2 columns; iOS JSON: x/y/z
    extract: r =>
      magnitude(r, 'double_values_0', 'double_values_1', 'double_values_2') ??
      magnitude(r, 'x', 'y', 'z'),
  },
  {
    key: 'gyroscope',
    label: 'Gyroscope',
    unit: 'rad/s',
    color: '#ef4444',
    platform: 'shared',
    // Android: double_values_0/1/2 columns; iOS JSON: x/y/z
    extract: r =>
      magnitude(r, 'double_values_0', 'double_values_1', 'double_values_2') ??
      magnitude(r, 'x', 'y', 'z'),
  },
  {
    key: 'locations',
    label: 'GPS Speed',
    unit: 'm/s',
    color: '#10b981',
    platform: 'shared',
    // Android: double_speed column; iOS JSON: speed
    extract: r => (r.double_speed as number | null) ?? (r.speed as number | null) ?? null,
  },
  {
    key: 'wifi',
    label: 'WiFi RSSI',
    unit: 'dBm',
    color: '#8b5cf6',
    platform: 'shared',
    // Android: rssi column; iOS JSON: rssi
    extract: r => (r.rssi as number | null) ?? null,
  },
  {
    key: 'bluetooth',
    label: 'Bluetooth RSSI',
    unit: 'dBm',
    color: '#06b6d4',
    platform: 'shared',
    // Android: bt_rssi column; iOS JSON: rssi
    extract: r => (r.bt_rssi as number | null) ?? (r.rssi as number | null) ?? null,
  },
  {
    key: 'calls',
    label: 'Call Duration',
    unit: 's',
    color: '#f97316',
    platform: 'shared',
    // Android: call_duration column; iOS JSON: call_duration
    extract: r => (r.call_duration as number | null) ?? null,
  },

  // ── Android only ─────────────────────────────────────────────────────────
  {
    key: 'light',
    label: 'Light',
    unit: 'lux',
    color: '#fbbf24',
    platform: 'android',
    // Android: double_values_0 column (the raw lux reading)
    extract: r => (r.double_values_0 as number | null) ?? null,
  },

  // ── iOS only ─────────────────────────────────────────────────────────────
  {
    key: 'pedometer',
    label: 'Step Count',
    unit: 'steps',
    color: '#ec4899',
    platform: 'ios',
    // iOS JSON: step_count or steps (plugin_ios_pedometer table)
    extract: r => (r.step_count as number | null) ?? (r.steps as number | null) ?? null,
  },
]

export function sensorsForPlatform(platform: 'android' | 'ios'): SensorConfig[] {
  return SENSOR_CONFIGS.filter(s => s.platform === 'shared' || s.platform === platform)
}
