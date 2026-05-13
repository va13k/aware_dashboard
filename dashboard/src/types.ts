export interface AndroidDevice {
  device_id: string;
  board?: string | null;
  brand?: string | null;
  device?: string | null;
  build_id?: string | null;
  hardware?: string | null;
  manufacturer: string | null;
  model: string | null;
  product?: string | null;
  serial?: string | null;
  release?: string | null;
  release_type?: string | null;
  sdk?: string | null;
  label?: string | null;
  last_seen: number;
  platform: "android";
}

export interface IosDevice {
  device_id: string;
  board?: string | null;
  brand?: string | null;
  device?: string | null;
  build_id?: string | null;
  hardware?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  product?: string | null;
  serial?: string | null;
  release?: string | null;
  release_type?: string | null;
  sdk?: string | null;
  label?: string | null;
  last_seen: number;
  platform: "ios";
}

export type Device = AndroidDevice | IosDevice;

export interface DevicesResponse {
  android: AndroidDevice[];
  ios: IosDevice[];
}

export interface DeviceStreamSummary {
  key: string;
  count: number;
  last_seen: number | null;
  latest: Record<string, unknown> | null;
}

export interface DeviceDetail {
  platform: "android" | "ios";
  device_id: string;
  device: Record<string, unknown> | null;
  streams: DeviceStreamSummary[];
}

export type SensorRecord = Record<string, unknown> & {
  id: number;
  timestamp: number;
  device_id: string;
};
