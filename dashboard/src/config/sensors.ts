import type { SensorRecord } from '../types'

export interface SensorConfig {
  key: string
  label: string
  unit: string
  color: string
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
  {
    key: 'battery',
    label: 'Battery Level',
    unit: '%',
    color: '#22c55e',
    extract: r => (r.battery_level as number | null) ?? (r.level as number | null) ?? null,
  },
  {
    key: 'screen',
    label: 'Screen Status',
    unit: '',
    color: '#3b82f6',
    extract: r => (r.screen_status as number | null) ?? null,
  },
  {
    key: 'accelerometer',
    label: 'Accelerometer',
    unit: 'm/s²',
    color: '#f59e0b',
    extract: r =>
      magnitude(r, 'double_values_0', 'double_values_1', 'double_values_2') ??
      magnitude(r, 'x', 'y', 'z'),
  },
  {
    key: 'gyroscope',
    label: 'Gyroscope',
    unit: 'rad/s',
    color: '#ef4444',
    extract: r =>
      magnitude(r, 'double_values_0', 'double_values_1', 'double_values_2') ??
      magnitude(r, 'x', 'y', 'z'),
  },
  {
    key: 'light',
    label: 'Light',
    unit: 'lux',
    color: '#fbbf24',
    extract: r =>
      (r.double_light_lux as number | null) ?? (r.lux as number | null) ?? null,
  },
  {
    key: 'wifi',
    label: 'WiFi RSSI',
    unit: 'dBm',
    color: '#8b5cf6',
    extract: r => (r.rssi as number | null) ?? null,
  },
  {
    key: 'bluetooth',
    label: 'Bluetooth RSSI',
    unit: 'dBm',
    color: '#06b6d4',
    extract: r => (r.bt_rssi as number | null) ?? (r.rssi as number | null) ?? null,
  },
]
