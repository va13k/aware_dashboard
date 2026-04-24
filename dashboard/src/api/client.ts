import type { DevicesResponse, SensorRecord } from '../types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const fetchDevices = (): Promise<DevicesResponse> =>
  get('/devices')

export const fetchSensor = (
  platform: 'android' | 'ios',
  deviceId: string,
  sensor: string,
  limit = 500,
): Promise<SensorRecord[]> =>
  get(`/${platform}/${encodeURIComponent(deviceId)}/${sensor}?limit=${limit}`)
