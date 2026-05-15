import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { SensorRecord } from "../types";
import ExportLink from "./ExportLink";

interface Props {
  foregroundRecords: SensorRecord[];
  crashRecords: SensorRecord[];
  historyRecords: SensorRecord[];
  notificationRecords: SensorRecord[];
  foregroundLoading: boolean;
  crashLoading: boolean;
  historyLoading: boolean;
  notificationLoading: boolean;
  exportHref?: string;
  className?: string;
}

const USER_FOREGROUND = "#9333ea";
const USER_NOTIFICATIONS = "#a855f7";
const USER_HISTORY = "#7c3aed";
const SYSTEM_COLOR = "#94a3b8";
const CRASH_COLOR = "#dc2626";

function normalizeTs(ts: number): number {
  return ts < 1e11 ? ts * 1000 : ts;
}

function fmtDuration(ms: number): string {
  if (ms < 1000) return "<1s";
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}m`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

function fmtTime(ts: number): string {
  return new Date(normalizeTs(ts)).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function appCountData(records: SensorRecord[]) {
  const counts: Record<string, { count: number; isSystem: boolean }> = {};
  for (const r of records) {
    const name =
      (r.application_name as string | null) ??
      (r.package_name as string | null) ??
      "Unknown";
    const isSystem = Boolean(r.is_system_app);
    if (!counts[name]) counts[name] = { count: 0, isSystem };
    counts[name].count++;
  }
  return Object.entries(counts)
    .map(([name, { count, isSystem }]) => ({ name, count, isSystem }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
}

function UserSystemLegend({ userColor }: { userColor: string }) {
  return (
    <div className="flex items-center gap-3 mb-2 text-[10px] text-sage">
      <span>
        <span
          className="inline-block w-1.5 h-1.5 rounded-full mr-1"
          style={{ background: userColor }}
        />
        user
      </span>
      <span>
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#94a3b8] mr-1" />
        system
      </span>
    </div>
  );
}

function AppHorizontalBar({
  data,
  userColor,
  valueFormatter,
  dataKey,
}: {
  data: { name: string; isSystem: boolean; [key: string]: unknown }[];
  userColor: string;
  valueFormatter?: (v: number) => string;
  dataKey: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 26)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 2, right: 12, left: 4, bottom: 0 }}
      >
        <XAxis
          type="number"
          tick={{ fill: "#5f746b", fontSize: 10 }}
          tickFormatter={valueFormatter}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ fill: "#5f746b", fontSize: 10 }}
          width={120}
          tickFormatter={(v: string) =>
            v.length > 18 ? v.slice(0, 17) + "…" : v
          }
        />
        <Tooltip
          contentStyle={{
            background: "#fffdf8",
            border: "1px solid rgba(48,67,54,0.14)",
            borderRadius: 10,
          }}
          labelStyle={{ color: "#5f746b" }}
          itemStyle={{ color: "#193229" }}
          formatter={
            valueFormatter
              ? (v: unknown) => [valueFormatter(Number(v))]
              : undefined
          }
        />
        <Bar dataKey={dataKey} radius={[0, 4, 4, 0]}>
          {data.map((entry) => (
            <Cell
              key={entry.name}
              fill={entry.isSystem ? SYSTEM_COLOR : userColor}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SubcardShell({
  color,
  title,
  note,
  children,
}: {
  color: string;
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-wire bg-card-strong/70 p-3 min-w-0">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: color }}
        />
        <h4 className="text-[12px] font-semibold text-ink flex-1">{title}</h4>
        {note && <span className="text-[10px] text-sage">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-28 flex items-center justify-center text-sage text-[12px]">
      No data
    </div>
  );
}

function ForegroundSubcard({
  records,
  loading,
}: {
  records: SensorRecord[];
  loading: boolean;
}) {
  const data = appCountData(records);
  return (
    <SubcardShell
      color={USER_FOREGROUND}
      title="Foreground"
      note={records.length > 0 ? `${records.length} events` : undefined}
    >
      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !data.length ? (
        <EmptyState />
      ) : (
        <>
          <UserSystemLegend userColor={USER_FOREGROUND} />
          <AppHorizontalBar
            data={data}
            userColor={USER_FOREGROUND}
            dataKey="count"
          />
        </>
      )}
    </SubcardShell>
  );
}

function NotificationsSubcard({
  records,
  loading,
}: {
  records: SensorRecord[];
  loading: boolean;
}) {
  const data = appCountData(records);
  return (
    <SubcardShell
      color={USER_NOTIFICATIONS}
      title="Notifications"
      note={records.length > 0 ? `${records.length} total` : undefined}
    >
      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !data.length ? (
        <EmptyState />
      ) : (
        <>
          <UserSystemLegend userColor={USER_NOTIFICATIONS} />
          <AppHorizontalBar
            data={data}
            userColor={USER_NOTIFICATIONS}
            dataKey="count"
          />
        </>
      )}
    </SubcardShell>
  );
}

function HistorySubcard({
  records,
  loading,
}: {
  records: SensorRecord[];
  loading: boolean;
}) {
  const appMap: Record<
    string,
    { totalMs: number; sessions: number; isSystem: boolean }
  > = {};
  for (const r of records) {
    const name =
      (r.application_name as string | null) ??
      (r.package_name as string | null) ??
      "Unknown";
    const startMs = normalizeTs(r.timestamp as number);
    const endMs = normalizeTs(
      (r.double_end_timestamp as number) || (r.timestamp as number),
    );
    const durationMs = Math.max(0, endMs - startMs);
    if (!appMap[name])
      appMap[name] = {
        totalMs: 0,
        sessions: 0,
        isSystem: Boolean(r.is_system_app),
      };
    appMap[name].totalMs += durationMs;
    appMap[name].sessions++;
  }

  const data = Object.entries(appMap)
    .map(([name, v]) => ({ name, ...v }))
    .sort((a, b) => b.totalMs - a.totalMs)
    .slice(0, 8);

  return (
    <SubcardShell
      color={USER_HISTORY}
      title="Session History"
      note={records.length > 0 ? `${records.length} sessions` : undefined}
    >
      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !data.length ? (
        <EmptyState />
      ) : (
        <>
          <UserSystemLegend userColor={USER_HISTORY} />
          <AppHorizontalBar
            data={data}
            userColor={USER_HISTORY}
            dataKey="totalMs"
            valueFormatter={fmtDuration}
          />
        </>
      )}
    </SubcardShell>
  );
}

function CrashesSubcard({
  records,
  loading,
}: {
  records: SensorRecord[];
  loading: boolean;
}) {
  const sorted = [...records].sort(
    (a, b) => (b.timestamp as number) - (a.timestamp as number),
  );
  const uniqueApps = new Set(
    records.map(
      (r) =>
        (r.application_name as string | null) ??
        (r.package_name as string | null),
    ),
  ).size;

  return (
    <SubcardShell
      color={CRASH_COLOR}
      title="Crashes"
      note={
        records.length > 0
          ? `${records.length} total · ${uniqueApps} app${uniqueApps !== 1 ? "s" : ""}`
          : undefined
      }
    >
      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !sorted.length ? (
        <div className="h-28 flex items-center justify-center text-sage text-[12px]">
          No crashes
        </div>
      ) : (
        <div className="overflow-y-auto max-h-50 flex flex-col gap-1 pr-0.5">
          {sorted.map((r) => (
            <div
              key={r.id as number}
              className="rounded-xl bg-card px-2.5 py-1.5 flex flex-col gap-0.5"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-ink truncate">
                  {(r.application_name as string | null) ??
                    (r.package_name as string | null) ??
                    "Unknown"}
                </span>
                <span className="text-[10px] text-sage shrink-0">
                  {fmtTime(r.timestamp as number)}
                </span>
              </div>
              {r.error_short != null && (
                <span className="text-[11px] text-red-500 truncate">
                  {r.error_short as string}
                </span>
              )}
              <div className="flex items-center gap-1.5">
                {(r.application_version as number | null) != null &&
                  (r.application_version as number) !== 0 && (
                    <span className="text-[10px] text-sage">
                      v{r.application_version as number}
                    </span>
                  )}
                {Boolean(r.is_system_app) && (
                  <span className="rounded-md bg-wire/60 px-1.5 py-0.5 text-[10px] text-sage">
                    system
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </SubcardShell>
  );
}

export default function ApplicationsCard({
  foregroundRecords,
  crashRecords,
  historyRecords,
  notificationRecords,
  foregroundLoading,
  crashLoading,
  historyLoading,
  notificationLoading,
  exportHref,
  className = "",
}: Props) {
  const totalRecords =
    foregroundRecords.length +
    crashRecords.length +
    historyRecords.length +
    notificationRecords.length;

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#9333ea]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Applications
        </h3>
        {totalRecords > 0 && (
          <span className="text-[11px] text-sage">
            {totalRecords.toLocaleString()} records
          </span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      <div className="grid grid-cols-1 gap-3 min-[760px]:grid-cols-2">
        <ForegroundSubcard
          records={foregroundRecords}
          loading={foregroundLoading}
        />
        <NotificationsSubcard
          records={notificationRecords}
          loading={notificationLoading}
        />
        <HistorySubcard records={historyRecords} loading={historyLoading} />
        <CrashesSubcard records={crashRecords} loading={crashLoading} />
      </div>
    </div>
  );
}
