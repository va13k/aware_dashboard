import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorRecord } from "../types";
import { fmt, max, min } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  batteryRecords: SensorRecord[];
  batteryLoading: boolean;
  chargesRecords: SensorRecord[];
  dischargesRecords: SensorRecord[];
  chargesLoading: boolean;
  dischargesLoading: boolean;
  batteryExportHref?: string;
  chargesExportHref?: string;
  dischargesExportHref?: string;
  className?: string;
}

const BATTERY_COLOR = "#22c55e";
const CHARGE_COLOR = "#16a34a";
const DISCHARGE_COLOR = "#f59e0b";

function normalizeTs(ts: number): number {
  return ts < 1e11 ? ts * 1000 : ts;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function fmtTime(ts: number): string {
  return new Date(ts).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function makeTickFormatter(spanMs: number) {
  const multiDay = spanMs > 24 * 60 * 60 * 1000;
  return (ts: number) => {
    const d = new Date(ts);
    if (multiDay) {
      return (
        d.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " " +
        d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    }
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };
}

interface ChargeEvent {
  id: number;
  timestamp: number;
  start: number | null;
  end: number | null;
  delta: number | null;
}

function extractEvents(records: SensorRecord[]): ChargeEvent[] {
  return records
    .map((r) => {
      const start = numberValue(r.battery_start);
      const end = numberValue(r.battery_end);
      return {
        id: r.id as number,
        timestamp: normalizeTs(r.timestamp as number),
        start,
        end,
        delta: start != null && end != null ? end - start : null,
      };
    })
    .sort((a, b) => b.timestamp - a.timestamp);
}

function SubcardShell({
  color,
  title,
  note,
  exportHref,
  children,
}: {
  color: string;
  title: string;
  note?: string;
  exportHref?: string;
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
        {exportHref && <ExportLink href={exportHref} />}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-28 flex items-center justify-center text-sage text-[12px]">
      No {label}
    </div>
  );
}

function DeltaTooltip({
  active,
  payload,
  isCharge,
}: {
  active?: boolean;
  payload?: {
    payload: {
      timestamp: number;
      delta: number | null;
      start: number | null;
      end: number | null;
    };
  }[];
  isCharge?: boolean;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      className="rounded-xl border px-3 py-2 text-[11px]"
      style={{ background: "#fffdf8", borderColor: "rgba(48,67,54,0.14)" }}
    >
      <div className="text-sage mb-1">{fmtTime(d.timestamp)}</div>
      {d.start != null && d.end != null && (
        <div className="text-ink font-semibold">
          {d.start}% → {d.end}%
        </div>
      )}
      {d.delta != null && (
        <div style={{ color: isCharge ? CHARGE_COLOR : DISCHARGE_COLOR }}>
          {d.delta >= 0 ? "+" : ""}
          {d.delta}%
        </div>
      )}
    </div>
  );
}

function BatteryLevelSection({
  records,
  loading,
  exportHref,
}: {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}) {
  const data = records
    .map((r) => ({
      time: r.timestamp,
      value: numberValue(r.battery_level) ?? numberValue(r.level) ?? numberValue(r.batteryLevel),
    }))
    .filter((r): r is { time: number; value: number } => r.value !== null)
    .sort((a, b) => a.time - b.time);

  const values = data.map((d) => d.value);
  const lastVal = values.length ? values[values.length - 1] : null;
  const spanMs =
    data.length > 1 ? data[data.length - 1].time - data[0].time : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="rounded-2xl border border-wire bg-card-strong/70 p-3 min-w-0">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: BATTERY_COLOR }}
        />
        <h4 className="text-[12px] font-semibold text-ink flex-1">Level</h4>
        <span className="text-[10px] text-sage">%</span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {loading ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : !values.length ? (
        <div className="h-40 flex items-center justify-center text-sage text-[12px]">
          No data
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 mb-2 text-[10px] text-sage">
            <span>
              <b className="text-ink">{values.length}</b> pts
            </span>
            <span>
              last <b className="text-ink">{fmt(lastVal!)}</b>%
            </span>
            <span>
              ↓ <b className="text-ink">{fmt(min(values))}</b>%
            </span>
            <span>
              ↑ <b className="text-ink">{fmt(max(values))}</b>%
            </span>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart
              data={data}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(48,67,54,0.12)"
              />
              <XAxis
                dataKey="time"
                tickFormatter={tickFormatter}
                tick={{ fill: "#5f746b", fontSize: 10 }}
                minTickGap={60}
              />
              <YAxis
                tick={{ fill: "#5f746b", fontSize: 10 }}
                width={36}
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
              />
              <Tooltip
                labelFormatter={(v) => new Date(v as number).toLocaleString()}
                formatter={(v: unknown) => [`${Number(v)}%`, "Level"]}
                contentStyle={{
                  background: "#fffdf8",
                  border: "1px solid rgba(48,67,54,0.14)",
                  borderRadius: 10,
                }}
                labelStyle={{ color: "#5f746b" }}
                itemStyle={{ color: "#193229" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={BATTERY_COLOR}
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-[10px] text-sage leading-snug">
            iPhone battery values are approximate and are usually reported in
            5% increments.
          </p>
        </>
      )}
    </div>
  );
}

function EventsSubcard({
  records,
  loading,
  color,
  title,
  isCharge,
  exportHref,
}: {
  records: SensorRecord[];
  loading: boolean;
  color: string;
  title: string;
  isCharge: boolean;
  exportHref?: string;
}) {
  const events = extractEvents(records);
  const chartData = [...events]
    .filter((e) => e.delta != null)
    .sort((a, b) => a.timestamp - b.timestamp);

  const deltas = events
    .map((e) => e.delta)
    .filter((d): d is number => d != null);
  const avgDelta = deltas.length
    ? Math.round(deltas.reduce((s, d) => s + d, 0) / deltas.length)
    : null;

  return (
    <SubcardShell
      color={color}
      title={title}
      note={events.length > 0 ? `${events.length} events` : undefined}
      exportHref={exportHref}
    >
      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !events.length ? (
        <EmptyState label={title.toLowerCase()} />
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-3 text-[10px] text-sage">
            {avgDelta != null && (
              <span>
                avg Δ{" "}
                <b className="text-ink">
                  {avgDelta >= 0 ? "+" : ""}
                  {avgDelta}%
                </b>
              </span>
            )}
            <span>
              total <b className="text-ink">{events.length}</b>
            </span>
          </div>

          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={100}>
              <ScatterChart margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="timestamp"
                  type="number"
                  domain={["auto", "auto"]}
                  tickFormatter={(v) =>
                    new Date(v as number).toLocaleDateString([], {
                      month: "numeric",
                      day: "numeric",
                    })
                  }
                  tick={{ fill: "#5f746b", fontSize: 10 }}
                  minTickGap={40}
                />
                <YAxis
                  dataKey="delta"
                  type="number"
                  tick={{ fill: "#5f746b", fontSize: 10 }}
                  width={32}
                  tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`}
                />
                <Tooltip
                  content={<DeltaTooltip isCharge={isCharge} />}
                  cursor={{ strokeDasharray: "3 3" }}
                />
                <ReferenceLine y={0} stroke="rgba(48,67,54,0.2)" />
                <Scatter
                  data={chartData.filter((e) => (e.delta ?? 0) >= 0)}
                  fill={color}
                />
                <Scatter
                  data={chartData.filter((e) => (e.delta ?? 0) < 0)}
                  fill="#ef4444"
                />
              </ScatterChart>
            </ResponsiveContainer>
          )}

          <div className="overflow-y-auto max-h-40 flex flex-col gap-1 pr-0.5 mt-1">
            {events.map((e) => (
              <div
                key={e.id}
                className="rounded-xl bg-card px-2.5 py-1.5 flex items-center gap-2"
              >
                <span className="text-[10px] text-sage shrink-0">
                  {fmtTime(e.timestamp)}
                </span>
                {e.start != null && e.end != null ? (
                  <span className="text-[11px] text-ink font-semibold flex-1">
                    {e.start}% → {e.end}%
                  </span>
                ) : (
                  <span className="text-[11px] text-sage flex-1">—</span>
                )}
                {e.delta != null && (
                  <span
                    className="text-[11px] font-semibold shrink-0"
                    style={{ color: e.delta >= 0 ? color : "#ef4444" }}
                  >
                    {e.delta >= 0 ? "+" : ""}
                    {e.delta}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </SubcardShell>
  );
}

export default function BatteryEventsCard({
  batteryRecords,
  batteryLoading,
  chargesRecords,
  dischargesRecords,
  chargesLoading,
  dischargesLoading,
  batteryExportHref,
  chargesExportHref,
  dischargesExportHref,
  className = "",
}: Props) {
  const totalRecords =
    batteryRecords.length + chargesRecords.length + dischargesRecords.length;

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#22c55e]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">Battery</h3>
        {totalRecords > 0 && (
          <span className="text-[11px] text-sage">
            {totalRecords.toLocaleString()} records
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 min-[760px]:grid-cols-2">
        <div className="col-span-1 min-[760px]:col-span-2">
          <BatteryLevelSection
            records={batteryRecords}
            loading={batteryLoading}
            exportHref={batteryExportHref}
          />
        </div>
        <EventsSubcard
          records={chargesRecords}
          loading={chargesLoading}
          color={CHARGE_COLOR}
          title="Charges"
          isCharge={true}
          exportHref={chargesExportHref}
        />
        <EventsSubcard
          records={dischargesRecords}
          loading={dischargesLoading}
          color={DISCHARGE_COLOR}
          title="Discharges"
          isCharge={false}
          exportHref={dischargesExportHref}
        />
      </div>
    </div>
  );
}
