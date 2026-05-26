import type { DeviceDetail, DevicesResponse, OverviewResponse, SensorRecord } from "../types";

export const BASE = "/api";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", signal });
  if (res.redirected && res.url.includes("/auth/")) {
    window.location.assign(res.url);
    return new Promise<T>(() => {});
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const fetchDevices = (): Promise<DevicesResponse> => get("/devices");

export const fetchOverview = (): Promise<OverviewResponse> => get("/overview");

export const fetchDeviceDetail = (
  platform: "android" | "ios",
  deviceId: string,
): Promise<DeviceDetail> =>
  get(`/devices/${platform}/${encodeURIComponent(deviceId)}`);

export const fetchSensor = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
  limit = 500,
  signal?: AbortSignal,
): Promise<SensorRecord[]> =>
  get(`/${platform}/${encodeURIComponent(deviceId)}/${sensor}?limit=${limit}`, signal);

export const exportAllHref = (): string => `${BASE}/export/all.zip`;

export const exportDeviceHref = (
  platform: "android" | "ios",
  deviceId: string,
): string => `${BASE}/export/device/${platform}/${encodeURIComponent(deviceId)}.zip`;

export const exportSensorHref = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
): string => {
  const params = new URLSearchParams({ sensor });
  return `${BASE}/${platform}/${encodeURIComponent(deviceId)}/export?${params.toString()}`;
};
