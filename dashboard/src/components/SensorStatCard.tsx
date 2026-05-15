import type { SensorConfig } from "../config/sensors";
import type { SensorRecord } from "../types";
import { min, max, fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  config: SensorConfig;
  androidRecords: SensorRecord[];
  iosRecords: SensorRecord[];
  loading: boolean;
  className?: string;
  androidExportHref?: string;
  iosExportHref?: string;
}

interface PlatformStats {
  count: number;
  last: number;
  min: number;
  max: number;
}

function platformStats(
  config: SensorConfig,
  records: SensorRecord[],
): PlatformStats | null {
  if (config.countOnly) {
    if (!records.length) return null;
    const latest = records.reduce((a, b) =>
      b.timestamp > a.timestamp ? b : a,
    );
    return {
      count: records.length,
      last: latest.timestamp,
      min: latest.timestamp,
      max: latest.timestamp,
    };
  }

  const pairs = records
    .map((r) => ({ ts: r.timestamp, v: config.extract(r) }))
    .filter((x): x is { ts: number; v: number } => x.v !== null);
  if (!pairs.length) return null;
  const values = pairs.map((p) => p.v);
  const latest = pairs.reduce((a, b) => (b.ts > a.ts ? b : a));
  return {
    count: values.length,
    last: latest.v,
    min: min(values),
    max: max(values),
  };
}

interface StatItemProps {
  label: string;
  children: React.ReactNode;
}

function StatItem({ label, children }: StatItemProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-[0.5px] text-sage">
        {label}
      </span>
      <span className="text-[15px] font-bold leading-none text-ink">
        {children}
      </span>
    </div>
  );
}

function formatStatValue(config: SensorConfig, value: number): string {
  if (config.countOnly) return new Date(value).toLocaleDateString();
  return config.enumLabels?.[value] ?? fmt(value);
}

export default function SensorStatCard({
  config,
  androidRecords,
  iosRecords,
  loading,
  className = "",
  androidExportHref,
  iosExportHref,
}: Props) {
  const android = platformStats(config, androidRecords);
  const ios = platformStats(config, iosRecords);
  const hasData = android || ios;
  const androidEmpty = !loading && androidRecords.length === 0;
  const iosEmpty = !loading && iosRecords.length === 0;

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: config.color }}
        />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          {config.label}
        </h3>
        {config.unit && (
          <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
            {config.unit}
          </span>
        )}
        {androidExportHref && iosExportHref ? (
          <>
            <ExportLink
              href={androidExportHref}
              label="↓ Android"
              title="Download Android records as CSV ZIP"
              disabled={androidEmpty}
            />
            <ExportLink
              href={iosExportHref}
              label="↓ iOS"
              title="Download iOS records as CSV ZIP"
              disabled={iosEmpty}
            />
          </>
        ) : androidExportHref ? (
          <ExportLink
            href={androidExportHref}
            label="↓ Export"
            title="Download records as CSV ZIP"
            disabled={androidEmpty}
          />
        ) : iosExportHref ? (
          <ExportLink
            href={iosExportHref}
            label="↓ Export"
            title="Download records as CSV ZIP"
            disabled={iosEmpty}
          />
        ) : null}
      </div>

      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !hasData ? (
        <div className="h-28 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="flex gap-6">
          {android && (
            <div className="flex-1">
              <p className="text-[10px] uppercase tracking-[0.5px] text-sage mb-3">
                Android
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <StatItem label="records">
                  {android.count.toLocaleString()}
                </StatItem>
                {config.countOnly ? (
                  <StatItem label="last">
                    <span style={{ color: config.color }}>
                      {formatStatValue(config, android.last)}
                    </span>
                  </StatItem>
                ) : (
                  <>
                    <StatItem label="last">
                      <span style={{ color: config.color }}>
                        {formatStatValue(config, android.last)}
                      </span>
                    </StatItem>
                    <StatItem label="min">
                      {formatStatValue(config, android.min)}
                    </StatItem>
                    <StatItem label="max">
                      {formatStatValue(config, android.max)}
                    </StatItem>
                  </>
                )}
              </div>
            </div>
          )}
          {android && ios && <div className="w-px bg-wire self-stretch" />}
          {ios && (
            <div className="flex-1">
              <p className="text-[10px] uppercase tracking-[0.5px] text-sage mb-3">
                iOS
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <StatItem label="records">
                  {ios.count.toLocaleString()}
                </StatItem>
                {config.countOnly ? (
                  <StatItem label="last">
                    <span style={{ color: config.color }}>
                      {formatStatValue(config, ios.last)}
                    </span>
                  </StatItem>
                ) : (
                  <>
                    <StatItem label="last">
                      <span style={{ color: config.color }}>
                        {formatStatValue(config, ios.last)}
                      </span>
                    </StatItem>
                    <StatItem label="min">
                      {formatStatValue(config, ios.min)}
                    </StatItem>
                    <StatItem label="max">
                      {formatStatValue(config, ios.max)}
                    </StatItem>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
