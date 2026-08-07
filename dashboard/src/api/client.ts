import type {
  AndroidStudyEvent,
  DeviceDetail,
  DevicesResponse,
  Manifest,
  SensorRecord,
  SeriesBucket,
  StudyRequirements,
} from "../types";

export const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (res.redirected && res.url.includes("/auth/")) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.assign(`/auth/login?next=${next}`);
    return new Promise<T>(() => {});
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const fetchDevices = (): Promise<DevicesResponse> => get("/devices");

export const fetchDeviceDetail = (
  platform: "android" | "ios",
  deviceId: string,
): Promise<DeviceDetail> =>
  get(`/devices/${platform}/${encodeURIComponent(deviceId)}`);

export const fetchStudyEvents = (
  deviceId: string,
  limit = 50,
  offset = 0,
): Promise<AndroidStudyEvent[]> => {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return get(
    `/devices/android/${encodeURIComponent(deviceId)}/study-events?${params.toString()}`,
  );
};

export const fetchStudyRequirements = (): Promise<StudyRequirements> =>
  get("/study/requirements");

export const fetchSensor = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
  opts: { limit?: number; fromTs?: number; toTs?: number } = {},
): Promise<SensorRecord[]> => {
  const params = new URLSearchParams({ limit: String(opts.limit ?? 500) });
  if (opts.fromTs != null) params.set("from_ts", String(Math.floor(opts.fromTs)));
  if (opts.toTs != null) params.set("to_ts", String(Math.floor(opts.toTs)));
  return get(
    `/${platform}/${encodeURIComponent(deviceId)}/${sensor}?${params.toString()}`,
  );
};

/**
 * Server-bucketed sensor series: the window is aggregated into ~`buckets`
 * evenly-spaced points so density stays consistent for any range. Use this for
 * numeric sensors instead of pulling raw rows (which a wide window would cap to
 * an unrepresentative slice).
 */
export const fetchSensorSeries = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
  opts: { fromTs?: number; toTs?: number; buckets?: number } = {},
): Promise<SeriesBucket[]> => {
  const params = new URLSearchParams({ buckets: String(opts.buckets ?? 1500) });
  if (opts.fromTs != null)
    params.set("from_ts", String(Math.floor(opts.fromTs)));
  if (opts.toTs != null) params.set("to_ts", String(Math.floor(opts.toTs)));
  return get(
    `/${platform}/${encodeURIComponent(deviceId)}/${sensor}/series?${params.toString()}`,
  );
};

export const exportAllHref = (): string => `${BASE}/export/all.zip`;

export const fetchManifest = (): Promise<Manifest> => get("/export/manifest");

export const exportManifestHref = (): string => `${BASE}/export/manifest`;

export const exportDeviceHref = (
  platform: "android" | "ios",
  deviceId: string,
): string =>
  `${BASE}/export/device/${platform}/${encodeURIComponent(deviceId)}.zip`;

export const exportSensorZipHref = (
  platform: "android" | "ios",
  sensor: string,
): string =>
  `${BASE}/export/sensor/${platform}/${encodeURIComponent(sensor)}.zip`;

export const exportSensorHref = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
): string => {
  const params = new URLSearchParams({ sensor });
  return `${BASE}/${platform}/${encodeURIComponent(deviceId)}/export?${params.toString()}`;
};
