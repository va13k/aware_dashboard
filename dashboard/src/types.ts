export type StudyEnrollmentStatus = "in_study" | "left_study" | "unknown";
export type StudyConfigStatus = "current" | "stale" | "unknown";
export type StudyConfigStatusReason = "no_device_config" | "no_server_config";
export type StudyConsentContext = "initial" | "study_update";
export type StudyEventKind =
  | "joined"
  | "rejoined"
  | "updated"
  | "consent"
  | "left"
  | "other";
export type ConfigDiffKind = "changed" | "only_on_server" | "only_on_device";

/** What a device-list row shows: enrollment and config badges, nothing more. */
export interface AndroidStudyListSummary {
  enrollment_status: StudyEnrollmentStatus;
  last_study_event_at: number | null;
  config_status: StudyConfigStatus;
  diff_count: number;
}

export interface AndroidStudySummary {
  enrollment_status: StudyEnrollmentStatus;
  last_study_event_at: number | null;
  last_study_event: string | null;
  last_join_at: number | null;
  last_exit_at: number | null;
  last_rejoin_at: number | null;
  last_rejoin_pause_started_at: number | null;
  last_rejoin_pause_ms: number | null;
  config_id: string | null;
  config_updated_at: string | null;
  approved_consents: string[];
  declined_consents: string[];
  last_consent_at: number | null;
  consent_context: StudyConsentContext | null;
  event_count: number;
  /** Raw rows the API collapsed into the events above. */
  duplicate_row_count: number;
}

export interface AndroidStudyEvent {
  timestamp: number | null;
  kind: StudyEventKind;
  /** The original text the client reported, kept for unrecognised events. */
  message: string;
  occurrences: number;
  joined_at: number | null;
  updated_at: number | null;
  exited_at: number | null;
  approved_consents: string[];
  declined_consents: string[];
  consent_context: StudyConsentContext | null;
  config_id: string | null;
  config_updated_at: string | null;
}

export interface ConfigDiffRow {
  /** Dotted path into the config, e.g. `sensors.status_wifi`. */
  path: string;
  kind: ConfigDiffKind;
  server_value: unknown;
  device_value: unknown;
}

export interface ConfigDiff {
  config_status: StudyConfigStatus;
  status_reason: StudyConfigStatusReason | null;
  config_update_enabled: boolean;
  device_config_update_enabled: boolean;
  server_updated_at: string | null;
  device_updated_at: string | null;
  diff_count: number;
  rows: ConfigDiffRow[];
}

export interface SensorRequirement {
  sensor_key: string;
  required: boolean;
  /** The config settings that govern this stream. */
  settings: string[];
}

export interface PlatformRequirements {
  platform: "android" | "ios";
  /** False when no config was found for this platform. */
  available: boolean;
  sensors: SensorRequirement[];
  /** Enabled settings with no stream the dashboard can request. */
  required_without_stream: string[];
  unmapped_settings: string[];
  required_sensor_count: number;
}

export interface StudyRequirements {
  android: PlatformRequirements;
  ios: PlatformRequirements;
}

export interface AndroidDevice {
  device_id: string;
  board?: string | null;
  device?: string | null;
  build_id?: string | null;
  hardware?: string | null;
  manufacturer: string | null;
  model: string | null;
  product?: string | null;
  release?: string | null;
  sdk?: string | null;
  /** Null for a phone that joined the study but has never uploaded. */
  last_seen: number | null;
  platform: "android";
  study?: AndroidStudyListSummary | null;
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
  last_seen: number | null;
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
  /** Android only - iOS has no study log. */
  study?: AndroidStudySummary;
  config_diff?: ConfigDiff;
  study_events?: AndroidStudyEvent[];
}

export type SensorRecord = Record<string, unknown> & {
  id: number;
  timestamp: number;
  device_id: string;
};

/**
 * One bucket of a server-aggregated sensor series: the bucket start `t` (ms),
 * the mean `avg` with `lo`/`hi` extent, and the raw row count `n`. `avg/lo/hi`
 * are null for buckets of an event sensor that only reports counts.
 */
export interface SeriesBucket {
  t: number;
  avg: number | null;
  lo: number | null;
  hi: number | null;
  n: number;
}

/** One client operation-log line (`aware_log`). */
export interface AwareLogRow {
  id: number;
  timestamp: number;
  device_id: string;
  log_type: string | null;
  log_message: string | null;
}

/** A page of log lines with the total matching the active filters. */
export interface AwareLogPage {
  total: number;
  rows: AwareLogRow[];
}

export interface SensorManifestEntry {
  row_count: number;
  devices_with_data: number;
  first_timestamp: number | null;
  last_timestamp: number | null;
  fields: string[];
}

export interface PlatformManifest {
  device_count: number;
  sensors: Record<string, SensorManifestEntry>;
}

export interface Manifest {
  generated_at: string;
  platforms: {
    android: PlatformManifest;
    ios: PlatformManifest;
  };
}

/** How fresh the cached counts are, per platform. */
export interface CountsStatus {
  stale_after_seconds: number;
  /** One figure for both platforms: a pass writes both databases. */
  last_refreshed: number | null;
  age_seconds: number | null;
  stale: boolean;
  platforms: Record<
    "android" | "ios",
    { last_refreshed: number | null; age_seconds: number | null }
  >;
}
