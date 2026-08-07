import type {
  AndroidStudyEvent,
  AwareLogPage,
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

/** Filters shared by the log list, its export URL, and paging. */
export interface AndroidLogQuery {
  deviceId?: string;
  logType?: string;
  fromTs?: number;
  toTs?: number;
  q?: string;
  limit?: number;
  offset?: number;
}

function logParams(opts: AndroidLogQuery, includePaging = true): URLSearchParams {
  const params = new URLSearchParams();
  if (opts.deviceId) params.set("device_id", opts.deviceId);
  // An empty `logType` is a real filter (rows with no type); only `undefined`
  // means "any type", so send the param whenever it is defined.
  if (opts.logType != null) params.set("log_type", opts.logType);
  if (opts.fromTs != null) params.set("from_ts", String(Math.floor(opts.fromTs)));
  if (opts.toTs != null) params.set("to_ts", String(Math.floor(opts.toTs)));
  if (opts.q) params.set("q", opts.q);
  if (includePaging) {
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.offset != null) params.set("offset", String(opts.offset));
  }
  return params;
}

/** A page of Android client logs (`aware_log`) matching the filters. */
export const fetchAndroidLogs = (opts: AndroidLogQuery = {}): Promise<AwareLogPage> =>
  get(`/logs/android?${logParams(opts).toString()}`);

/** The distinct `log_type` values, for the "stream to track" filter. */
export const fetchAndroidLogTypes = (): Promise<string[]> =>
  get("/logs/android/log-types");

/** CSV download URL for the logs matching the filters (all rows, no paging). */
export const androidLogsExportHref = (opts: AndroidLogQuery = {}): string =>
  `${BASE}/logs/android/export?${logParams(opts, false).toString()}`;

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

/**
 * CSV download URL for one sensor over a window. Returns every raw row in the
 * `from`/`to` window at full resolution (the chart shows ~1500 bucketed points
 * of the same window). Omitting the bounds uses the server's default window
 * (see `clamp_window`).
 */
export const exportSensorHref = (
  platform: "android" | "ios",
  deviceId: string,
  sensor: string,
  opts: { fromTs?: number; toTs?: number } = {},
): string => {
  const params = new URLSearchParams({ sensor });
  if (opts.fromTs != null) params.set("from_ts", String(Math.floor(opts.fromTs)));
  if (opts.toTs != null) params.set("to_ts", String(Math.floor(opts.toTs)));
  return `${BASE}/${platform}/${encodeURIComponent(deviceId)}/export?${params.toString()}`;
};
