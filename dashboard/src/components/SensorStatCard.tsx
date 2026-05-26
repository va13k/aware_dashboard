import type { SensorConfig } from "../config/sensors";
import type { SensorOverviewStats } from "../types";

interface Props {
  config: SensorConfig;
  androidStats: SensorOverviewStats | null;
  iosStats: SensorOverviewStats | null;
  loading: boolean;
  className?: string;
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

function normalizeTs(ts: number): number {
  return ts < 100000000000 ? ts * 1000 : ts;
}

function formatLastSeen(ts: number | null): string {
  if (ts == null) return "–";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(normalizeTs(ts)));
}

function PlatformBlock({
  label,
  stats,
  color,
}: {
  label: string;
  stats: SensorOverviewStats;
  color: string;
}) {
  return (
    <div className="flex-1">
      <p className="text-[10px] uppercase tracking-[0.5px] text-sage mb-3">
        {label}
      </p>
      <div className="grid grid-cols-1 gap-y-3">
        <StatItem label="records">
          <span style={{ color }}>{stats.count.toLocaleString()}</span>
        </StatItem>
        <StatItem label="last seen">{formatLastSeen(stats.last_ts)}</StatItem>
      </div>
    </div>
  );
}

export default function SensorStatCard({
  config,
  androidStats,
  iosStats,
  loading,
  className = "",
}: Props) {
  const hasData = androidStats || iosStats;

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
      </div>

      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !hasData ? (
        <div className="h-28 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="flex gap-6">
          {androidStats && (
            <PlatformBlock
              label="Android"
              stats={androidStats}
              color={config.color}
            />
          )}
          {androidStats && iosStats && (
            <div className="w-px bg-wire self-stretch" />
          )}
          {iosStats && (
            <PlatformBlock label="iOS" stats={iosStats} color={config.color} />
          )}
        </div>
      )}
    </div>
  );
}
