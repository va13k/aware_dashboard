import type { SensorConfig } from "../config/sensors";
import type { SensorManifestEntry } from "../types";
import { absoluteDate } from "../utils/time";

interface Props {
  config: SensorConfig;
  /** Manifest stats for each platform, or null when the sensor has no data. */
  android: SensorManifestEntry | null;
  ios: SensorManifestEntry | null;
  loading: boolean;
  className?: string;
  /** Opens the export dialog for this sensor. */
  onExport?: () => void;
}

function hasRows(entry: SensorManifestEntry | null): entry is SensorManifestEntry {
  return !!entry && entry.row_count > 0;
}

function StatItem({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-[0.5px] text-sage">
        {label}
      </span>
      <span className="text-[16px] font-bold leading-none text-ink">
        {children}
      </span>
    </div>
  );
}

function PlatformStats({
  label,
  entry,
}: {
  label: string;
  entry: SensorManifestEntry;
}) {
  return (
    <div className="flex-1">
      <p className="text-[11px] uppercase tracking-[0.5px] text-sage mb-3">
        {label}
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <StatItem label="records">{entry.row_count.toLocaleString()}</StatItem>
        <StatItem label="devices">
          {entry.devices_with_data.toLocaleString()}
        </StatItem>
        <StatItem label="first">
          {entry.first_timestamp != null
            ? absoluteDate(entry.first_timestamp)
            : "—"}
        </StatItem>
        <StatItem label="last">
          {entry.last_timestamp != null
            ? absoluteDate(entry.last_timestamp)
            : "—"}
        </StatItem>
      </div>
    </div>
  );
}

/**
 * Study-wide coverage for one sensor: absolute record counts and devices with
 * data per platform, from the (cache-backed) manifest. Per-value stats live on
 * the device charts, so the overview stays a counts-and-coverage view.
 */
export default function SensorStatCard({
  config,
  android,
  ios,
  loading,
  className = "",
  onExport,
}: Props) {
  const androidHasRows = hasRows(android);
  const iosHasRows = hasRows(ios);
  const hasData = androidHasRows || iosHasRows;

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: config.color }}
        />
        <h3 className="text-[14px] font-semibold flex-1 text-ink">
          {config.label}
        </h3>
        {config.unit && (
          <span className="text-[12px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
            {config.unit}
          </span>
        )}
        {/* One control rather than a button per platform: the dialog behind it
            asks which platforms and which period, and those two questions
            belong together. */}
        {onExport ? (
          androidHasRows || iosHasRows || loading ? (
            <button
              type="button"
              onClick={onExport}
              title="Choose platforms and a period, then export"
              className="inline-flex h-7 items-center justify-center gap-1.5 rounded-lg border border-wire bg-card-strong px-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
            >
              ↓ Export
            </button>
          ) : (
            <span
              title="No records to export"
              className="inline-flex h-7 cursor-not-allowed items-center justify-center rounded-lg border border-wire bg-card-strong px-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage/30"
            >
              ↓ Export
            </span>
          )
        ) : null}
      </div>

      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !hasData ? (
        <div className="h-28 flex items-center justify-center text-sage text-[14px]">
          No data
        </div>
      ) : (
        <div className="flex gap-6">
          {androidHasRows && <PlatformStats label="Android" entry={android!} />}
          {androidHasRows && iosHasRows && (
            <div className="w-px bg-wire self-stretch" />
          )}
          {iosHasRows && <PlatformStats label="iOS" entry={ios!} />}
        </div>
      )}
    </div>
  );
}
