import type { DeviceDetail, DevicesResponse, SensorRecord } from '../types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (res.redirected && res.url.includes('/auth/')) {
    window.location.assign(res.url)
    return new Promise<T>(() => {})
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const fetchDevices = (): Promise<DevicesResponse> =>
  get('/devices')

export const fetchDeviceDetail = (
  platform: 'android' | 'ios',
  deviceId: string,
): Promise<DeviceDetail> =>
  get(`/devices/${platform}/${encodeURIComponent(deviceId)}`)

export const fetchSensor = (
  platform: 'android' | 'ios',
  deviceId: string,
  sensor: string,
  limit = 500,
): Promise<SensorRecord[]> =>
  get(`/${platform}/${encodeURIComponent(deviceId)}/${sensor}?limit=${limit}`)
