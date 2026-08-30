import type {
  AndroidStudyEvent,
  ChosenPeriod,
  CountsStatus,
  CoverageCounts,
  CoverageLevel,
  CoverageWindows,
  AwareLogPage,
  DeviceCoverage,
  DeviceDetail,
  EnrolmentWindow,
  DeviceExclusion,
  DevicesResponse,
  ExportPlatform,
  Manifest,
  OrphanCounts,
  SensorRecord,
  SeriesBucket,
  StudyCoverage,
  StudyDataflow,
  StudyRequirements,
  RefusalCounts,
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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
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

/** The same three calls against an iPhone's logs, which the API projects into
 *  the Android shape so one panel renders both. */
export const fetchIosLogs = (opts: AndroidLogQuery = {}): Promise<AwareLogPage> =>
  get(`/logs/ios?${logParams(opts).toString()}`);

export const fetchIosLogTypes = (): Promise<string[]> =>
  get("/logs/ios/log-types");

export const iosLogsExportHref = (opts: AndroidLogQuery = {}): string =>
  `${BASE}/logs/ios/export?${logParams(opts, false).toString()}`;

/** When the counts were last refreshed, and whether that is too long ago. */
export const fetchCountsStatus = (): Promise<CountsStatus> => get("/counts/status");

/** Rows whose Android insert supplied no device id, reported outside totals. */
export const fetchOrphanCounts = (): Promise<OrphanCounts> => get("/counts/orphans");

/** Where each platform's data goes, read from the config the phones were given. */
export const fetchStudyDataflow = (): Promise<StudyDataflow> =>
  get("/study/dataflow");

/** Writes refused at ingest, which store nothing and so appear nowhere else. */
export const fetchRefusals = (): Promise<RefusalCounts> =>
  get("/counts/refusals");

/** The periods on offer, each resolved to absolute bounds and what it holds. */
export const fetchCoverageWindows = (): Promise<CoverageWindows> =>
  get("/coverage/windows");

/** How many records a period holds, optionally narrowed to a platform or sensor. */
export const fetchCoverageCounts = (opts: {
  from?: number | null;
  to?: number | null;
  platform?: "android" | "ios" | null;
  sensor?: string | null;
  device?: string | null;
} = {}): Promise<CoverageCounts> => {
  const params = new URLSearchParams();
  if (opts.from != null) params.set("from_ts", String(Math.round(opts.from)));
  if (opts.to != null) params.set("to_ts", String(Math.round(opts.to)));
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.sensor) params.set("sensor", opts.sensor);
  if (opts.device) params.set("device", opts.device);
  const query = params.toString();
  return get(`/coverage/counts${query ? `?${query}` : ""}`);
};

/**
 * Record that a participant has left, closing their enrolment window.
 *
 * `leftAt` is when they *acted*, which a researcher usually learns after the
 * fact — sending it is what makes a late notice land on the right day instead of
 * marking every day since as expected-and-missing.
 */
export const withdrawDevice = (
  deviceId: string,
  opts: { leftAt?: number | null } = {},
): Promise<{ status: string; window: EnrolmentWindow }> =>
  post(`/devices/android/${encodeURIComponent(deviceId)}/withdraw`, {
    left_at: opts.leftAt ?? null,
  });

/**
 * Take a device out of the analysis, keeping its data in the database.
 *
 * Separate from withdrawal on purpose: withdrawal stops new data arriving, this
 * decides what happens to what was already collected. The device stays on screen
 * and leaves the exports.
 */
export const excludeDevice = (
  platform: "android" | "ios",
  deviceId: string,
  note = "",
): Promise<{ status: string; exclusion: DeviceExclusion }> =>
  post(`/devices/${platform}/${encodeURIComponent(deviceId)}/exclude`, { note });

/** Put a device back into the analysis, clearing the exclusion. */
export const includeDevice = (
  platform: "android" | "ios",
  deviceId: string,
): Promise<{ status: string }> =>
  post(`/devices/${platform}/${encodeURIComponent(deviceId)}/include`, {});

/** Undo a withdrawal, handing the device back to its own study log. */
export const reopenDeviceEnrolment = (
  deviceId: string,
): Promise<{ status: string }> =>
  post(`/devices/android/${encodeURIComponent(deviceId)}/rejoin`, {});

/** The parameters both coverage grids share. */
function gridParams(opts: {
  level: CoverageLevel;
  anchor: number;
  tz?: string | null;
}): URLSearchParams {
  const params = new URLSearchParams();
  params.set("level", opts.level);
  params.set("anchor", String(Math.round(opts.anchor)));
  if (opts.tz) params.set("tz", opts.tz);
  return params;
}

/** The study grid: a device per row, a bucket of `level` per column. */
export const fetchStudyCoverage = (opts: {
  level: CoverageLevel;
  anchor: number;
  platform?: "android" | "ios" | null;
  sensor?: string | null;
  tz?: string | null;
}): Promise<StudyCoverage> => {
  const params = gridParams(opts);
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.sensor) params.set("sensor", opts.sensor);
  return get(`/coverage/study?${params.toString()}`);
};

/** One phone's grid: a sensor per row, the same buckets. */
export const fetchDeviceCoverage = (
  platform: "android" | "ios",
  deviceId: string,
  opts: { level: CoverageLevel; anchor: number; tz?: string | null },
): Promise<DeviceCoverage> =>
  get(
    `/coverage/device/${platform}/${encodeURIComponent(deviceId)}?${gridParams(
      opts,
    ).toString()}`,
  );

/**
 * The grid on screen as an `.xlsx` workbook: the same buckets, the same counts,
 * each cell filled with its band's colour, and a total down every row and across
 * every column.
 *
 * Takes the whole view rather than a window, so the file holds what the
 * researcher was looking at instead of a layout of its own.
 */
export const studyCoverageWorkbookHref = (opts: {
  level: CoverageLevel;
  anchor: number;
  platform?: "android" | "ios" | null;
  sensor?: string | null;
  tz?: string | null;
}): string => {
  const params = gridParams(opts);
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.sensor) params.set("sensor", opts.sensor);
  return `${BASE}/coverage/study.xlsx?${params.toString()}`;
};

/** One phone's grid as a workbook: a sensor per row, the same buckets. */
export const deviceCoverageWorkbookHref = (
  platform: "android" | "ios",
  deviceId: string,
  opts: { level: CoverageLevel; anchor: number; tz?: string | null },
): string =>
  `${BASE}/coverage/device/${platform}/${encodeURIComponent(
    deviceId,
  )}/workbook.xlsx?${gridParams(opts).toString()}`;

/**
 * The reference-spreadsheet layout: one CSV per sensor inside a ZIP, devices
 * down and hours across, marked 1 where an hour holds a record.
 *
 * Hour columns whatever the level on screen, because this reproduces a fixed
 * layout for diffing rather than the grid the interface draws.
 */
export const coverageMatrixHref = (opts: {
  from: number;
  to: number;
  platform?: "android" | "ios" | null;
  tz?: string | null;
  values?: "presence" | "counts";
}): string => {
  const params = new URLSearchParams();
  params.set("from_ts", String(Math.round(opts.from)));
  params.set("to_ts", String(Math.round(opts.to)));
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.tz) params.set("tz", opts.tz);
  if (opts.values) params.set("values", opts.values);
  return `${BASE}/coverage/matrix?${params.toString()}`;
};

/**
 * Bounds as the export endpoints take them. Omitted entirely for all time, so
 * the server reads it as the whole table rather than as an empty window.
 */
export const periodParams = (period?: ChosenPeriod | null): string => {
  if (!period || (period.from == null && period.to == null)) return "";
  const params = new URLSearchParams();
  if (period.from != null) params.set("from_ts", String(Math.round(period.from)));
  if (period.to != null) params.set("to_ts", String(Math.round(period.to)));
  return `?${params.toString()}`;
};

export const exportAllHref = (
  period?: ChosenPeriod | null,
  platform: ExportPlatform = "all",
): string => {
  const params = periodParams(period);
  return `${BASE}/export/all.zip${params ? `${params}&` : "?"}platform=${platform}`;
};

export const fetchManifest = (): Promise<Manifest> => get("/export/manifest");

export const exportManifestHref = (): string => `${BASE}/export/manifest`;

export const exportDeviceHref = (
  platform: "android" | "ios",
  deviceId: string,
  period?: ChosenPeriod | null,
): string =>
  `${BASE}/export/device/${platform}/${encodeURIComponent(deviceId)}.zip${periodParams(period)}`;

export const exportSensorZipHref = (
  platform: ExportPlatform,
  sensor: string,
  period?: ChosenPeriod | null,
): string =>
  `${BASE}/export/sensor/${platform}/${encodeURIComponent(sensor)}.zip${periodParams(period)}`;

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

// Reaching a participant. The only call in this file that sends something outward
// rather than reading something back, which is why its result says what happened to
// the message rather than returning a record.
export interface SentMessage {
  _id: number;
  device_id: string;
  kind: string;
  title: string;
  sent_at: number;
  retained: number;
}

export interface MessageHistory {
  sent: SentMessage[];
  delivered: { device_id: string; topic: string; timestamp: number }[];
  answered: {
    device_id: string;
    esm_title: string;
    esm_user_answer: string;
    answered_at: number;
  }[];
}

/** One prompt the study put in front of a participant, and what came back. */
export interface DevicePrompt {
  shown_at: number;
  status: number;
  title: string | null;
  instructions: string | null;
  trigger_name: string | null;
  answer: string | null;
  answered_at: number | null;
  answered: boolean;
}

/**
 * What one participant was asked, from both sides.
 *
 * `prompts` are the ESMs their phone recorded — sent from here or raised by a
 * schedule — and only these carry an answer. `sent` is everything the dashboard
 * asked of the phone, including the kinds nothing comes back from: a notice is a
 * notification the client renders and writes nothing about, and sync and update
 * are instructions it acts on silently.
 */
export interface DeviceMessages {
  prompts: DevicePrompt[];
  sent: (SentMessage & { body: string | null })[];
}

export const fetchDeviceMessages = (deviceId: string): Promise<DeviceMessages> =>
  get(`/messages/for-device/${encodeURIComponent(deviceId)}`);

export interface SendMessageRequest {
  device_id?: string;
  device_ids?: string[];
  kind: "sync" | "update" | "question" | "esm" | "notice";
  title?: string;
  instructions?: string;
  answers?: string[];
  expires?: number;
  retain?: boolean;
}

export const sendMessage = (
  body: SendMessageRequest,
): Promise<{
  sent: string[];
  held: { device_id: string; reason: string }[];
  failed: { device_id: string; reason: string }[];
  recorded: boolean;
  retained?: boolean;
}> =>
  post("/messages/send", body);

export const fetchMessageHistory = (deviceId?: string): Promise<MessageHistory> =>
  get(`/messages/history${deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ""}`);
