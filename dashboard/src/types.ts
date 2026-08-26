export type StudyEnrollmentStatus = "in_study" | "left_study" | "unknown";
export type StudyConfigStatus = "current" | "differs" | "unknown";
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
  /**
   * Where the study sends its data, and where this phone currently thinks it
   * does. They differ across a switch until the phone fetches the new config.
   * `*_source` is "declared" when the config names it and "inferred" when it was
   * read back out of the webservice setting, which every config predating the
   * field is.
   */
  dataflow: string | null;
  dataflow_source: string | null;
  device_dataflow: string | null;
  device_dataflow_source: string | null;
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
  /** When this phone's first record arrived. Null before it has uploaded. */
  first_seen?: number | null;
  /** Null for a phone that joined the study but has never uploaded. */
  last_seen: number | null;
  platform: "android";
  study?: AndroidStudyListSummary | null;
  /** The enrolment span, including a first-data span inferred for coverage. */
  enrolment?: DeviceEnrolmentSummary | null;
  /**
   * Whether the study has a record of this device joining. False is the finding:
   * data arrived from a phone that left no trace of enrolling.
   */
  recognised?: boolean | null;
  /** Present when a researcher has taken this device out of the analysis. */
  excluded?: DeviceExclusion | null;
}

/**
 * A device a researcher has taken out of the analysis.
 *
 * Withdrawal stops new data arriving; this says what happens to the data already
 * collected. The rows stay in the database and the device stays on screen — what
 * changes is that it leaves the exports.
 */
export interface DeviceExclusion {
  excluded_at: number;
  note: string;
}

/** What a device row shows about enrolment: the span, and how it is known. */
export interface DeviceEnrolmentSummary {
  joined_at: number;
  left_at: number | null;
  join_source: string;
  window_count: number;
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
  first_seen?: number | null;
  last_seen: number | null;
  platform: "ios";
  /**
   * Always null: an iPhone keeps its study state on the phone and never uploads
   * it, so the server holds nothing to recognise it by.
   */
  recognised?: null;
  /** Present when a researcher has taken this device out of the analysis. */
  excluded?: DeviceExclusion | null;
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
  /** Android only: the enrolment span, including one inferred from first data. */
  enrolment?: DeviceEnrolmentSummary | null;
  /** Every window, so the gap between two of them reads as time off the study. */
  enrolment_windows?: EnrolmentWindow[];
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

/**
 * How much data a decision leaves out of the analysis, as a pair.
 *
 * Reported beside a figure rather than folded into it: the figure is what an
 * export writes, and this is what accounts for the difference from what
 * arrived.
 */
export interface ExcludedTotals {
  devices: number;
  records: number;
}

export interface SensorManifestEntry {
  /** Rows an export writes for this sensor: excluded devices are already out. */
  row_count: number;
  devices_with_data: number;
  /** The part of what arrived that exclusion holds back from this sensor. */
  excluded_row_count: number;
  excluded_devices: number;
  first_timestamp: number | null;
  last_timestamp: number | null;
  fields: string[];
}

export interface PlatformManifest {
  device_count: number;
  sensors: Record<string, SensorManifestEntry>;
  /** This platform's excluded devices and the rows they hold, study-wide. */
  excluded: ExcludedTotals;
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

export interface OrphanPlatformCounts {
  records: number;
  tables: Record<string, number>;
}

/** Rows stored without a device id and deliberately excluded from exports/totals. */
export interface OrphanCounts {
  records: number;
  cause: string;
  platforms: Record<"android" | "ios", OrphanPlatformCounts>;
}

/** One device the micro-server turned away, with both ends of the attempt. */
export interface Refusal {
  device_id: string;
  reason: string;
  explanation: string;
  attempts: number;
  rows_refused: number;
  last_table: string;
  first_seen: number;
  last_seen: number;
}

export interface RefusalPlatform {
  attempts: number;
  rows_refused: number;
  devices: number;
  refusals: Refusal[];
}

/**
 * Writes refused at ingest. Nothing was stored, so this is the only trace of the
 * attempt — a refused device leaves no rows for the device list to notice.
 */
export interface RefusalCounts {
  attempts: number;
  devices: number;
  platforms: Record<"android" | "ios", RefusalPlatform>;
}

/** Where a platform's data goes, and how the answer was established. */
export interface PlatformDataflow {
  dataflow: string | null;
  source: string | null;
}

export interface StudyDataflow {
  android: PlatformDataflow;
  ios: PlatformDataflow;
  config_available: boolean;
}

export type CoverageAnchor = "data" | "now";
export type CoveragePeriod = "hour" | "day" | "week" | "month" | "year";

/** One period on offer, already resolved to the instants it means. */
export interface CoverageWindow {
  key: string;
  anchor: CoverageAnchor;
  period: CoveragePeriod;
  label: string;
  from: number | null;
  to: number | null;
  available: boolean;
  records: number;
  platforms: Record<string, number>;
}

export interface CoverageWindows {
  now: number;
  newest: number | null;
  windows: CoverageWindow[];
  /** Totals count the whole hour a window's edge lands in. */
  hour_granular: boolean;
}

export interface CoverageCounts {
  from: number | null;
  to: number | null;
  /** What the download holds: the excluded devices are already left out. */
  total: number;
  platforms: Record<string, number>;
  sensors: Record<string, Record<string, number>>;
  /** What exclusion holds back, over the same period, sensor and platform. */
  excluded: ExcludedTotals;
  available: boolean;
  hour_granular: boolean;
  /** Roughly what the download will weigh. A magnitude, not a promise. */
  estimated_bytes: number;
}

/** The bucket width a coverage grid is drawn at, named after the bucket. */
export type CoverageLevel = "month" | "day" | "hour";

/** What a cell says about its bucket. */
export type CoverageState =
  /** Outside every enrolment window: neutral, not a gap. */
  | "not_expected"
  /** At or above what the configured rate implies. */
  | "reporting"
  /** Some data, materially less than the configured rate implies. */
  | "under"
  /** Expected and absent. */
  | "missing"
  /** Data arrived, with no configured rate to judge the amount against. */
  | "present";

/** One column of a grid. */
export interface CoverageBucket {
  key: string;
  label: string;
  from: number;
  to: number;
}

export interface CoverageCell {
  state: CoverageState;
  /**
   * Which colour band the cell falls in, decided by the API so the grid and the
   * downloadable workbook are coloured from one answer.
   */
  band?: string;
  records: number;
  /** Hours of this bucket the device was enrolled for. */
  hours: number;
  /** Records the config implies for the covered part, when it implies any. */
  expected?: number | null;
  basis?: string | null;
  /** The expectation bounds scans rather than rows, so it is a lower bound. */
  floor?: boolean;
  /** Aggregate cells only: required sensors reporting, out of how many. */
  reporting?: number;
  required?: number;
  fraction?: number | null;
}

export interface EnrolmentWindow {
  joined_at: number;
  left_at: number | null;
  join_source: string;
  left_source: string | null;
}

export interface CoverageRow {
  device_id: string;
  platform: "android" | "ios";
  enrolment_windows: EnrolmentWindow[];
  cells: CoverageCell[];
  records: number;
  /**
   * Present when a researcher has left this device out of the analysis. The cells
   * still report what arrived: what was collected is a fact, and the exclusion is
   * a decision about it.
   */
  excluded?: DeviceExclusion | null;
}

/** One excluded device, with the amount of data the exclusion leaves out. */
export interface ExcludedRow extends DeviceExclusion {
  device_id: string;
  platform: "android" | "ios";
  records: number;
}

/**
 * What the exports leave out. Counted all-time rather than over the visible span,
 * because the exports an exclusion governs are not bounded by what the grid is
 * showing.
 */
export interface ExcludedSummary {
  devices: number;
  records: number;
  rows: ExcludedRow[];
}

interface CoverageGridBase {
  level: CoverageLevel;
  /** The level a column click opens, or null at the finest. */
  drills_into: CoverageLevel | null;
  anchor: number;
  timezone: string;
  from: number;
  to: number;
  buckets: CoverageBucket[];
  /** The busiest cell, so every row shades against one ceiling. */
  max_records: number;
  hour_granular: boolean;
}

export interface StudyCoverage extends CoverageGridBase {
  sensor: string | null;
  platforms: ("android" | "ios")[];
  rows: CoverageRow[];
  required_sensors: Record<string, string[]>;
  excluded: ExcludedSummary;
}

export interface DeviceCoverageRow {
  sensor: string;
  required: boolean;
  cells: CoverageCell[];
  records: number;
  expected_per_hour: number | null;
  basis: string | null;
}

export interface DeviceCoverage extends CoverageGridBase {
  platform: "android" | "ios";
  device_id: string;
  enrolment_windows: EnrolmentWindow[];
  rows: DeviceCoverageRow[];
}

/** Which side of a sensor card an export covers. */
export type ExportPlatform = "all" | "android" | "ios";

/**
 * What the researcher picked. `from`/`to` null on both ends means all time,
 * which is an explicit choice rather than the absence of one.
 */
export interface ChosenPeriod {
  from: number | null;
  to: number | null;
  label: string;
}
