export interface AndroidDevice {
  device_id: string
  manufacturer: string | null
  model: string | null
  last_seen: number
  platform: 'android'
}

export interface IosDevice {
  device_id: string
  last_seen: number
  platform: 'ios'
}

export type Device = AndroidDevice | IosDevice

export interface DevicesResponse {
  android: AndroidDevice[]
  ios: IosDevice[]
}

export type SensorRecord = Record<string, unknown> & {
  id: number
  timestamp: number
  device_id: string
}
