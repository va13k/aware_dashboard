import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorRecord } from "../types";
import { fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

interface UsagePoint {
  time: number;
  onMs: number;
  offMs: number;
  onMinutes: number;
  offMinutes: number;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return "0 s";
  const seconds = ms / 1000;
  if (seconds < 60) return `${fmt(seconds, 1)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${fmt(minutes, 1)} min`;
  return `${fmt(minutes / 60, 1)} h`;
}

function makeTickFormatter(spanMs: number) {
  const multiDay = spanMs > 24 * 60 * 60 * 1000;
  return (ts: number) => {
    const date = new Date(ts);
    if (multiDay) {
      return (
        date.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " " +
        date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    }
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };
}

function buildData(records: SensorRecord[]): UsagePoint[] {
  return records
    .map((record): UsagePoint | null => {
      const onMs = Math.max(0, numberValue(record.elapsed_device_on) ?? 0);
      const offMs = Math.max(0, numberValue(record.elapsed_device_off) ?? 0);
      if (onMs === 0 && offMs === 0) return null;
      return {
        time: record.timestamp,
        onMs,
        offMs,
        onMinutes: onMs / 60000,
        offMinutes: offMs / 60000,
      };
    })
    .filter((point): point is UsagePoint => point != null)
    .sort((a, b) => a.time - b.time);
}

export default function DeviceUsageRecordsCard({
  records,
  loading,
  exportHref,
}: Props) {
  const data = buildData(records);
  const onEvents = data.filter((point) => point.onMs > 0).length;
  const offEvents = data.filter((point) => point.offMs > 0).length;
  const totalOnMs = data.reduce((sum, point) => sum + point.onMs, 0);
  const totalOffMs = data.reduce((sum, point) => sum + point.offMs, 0);
  const last = data.length ? data[data.length - 1] : null;
  const spanMs = data.length > 1 ? data[data.length - 1].time - data[0].time : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#9333ea]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Device Usage
        </h3>
        <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
          duration
        </span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {records.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[11px] text-sage">
          <span>
            <b className="text-ink">{records.length.toLocaleString()}</b> records
          </span>
          <span>
            on intervals <b className="text-ink">{onEvents.toLocaleString()}</b>
          </span>
          <span>
            off intervals <b className="text-ink">{offEvents.toLocaleString()}</b>
          </span>
          {last && (
            <span>
              last{" "}
              <b className="text-ink">
                {last.onMs > 0 ? "on" : "off"}{" "}
                {formatDuration(last.onMs > 0 ? last.onMs : last.offMs)}
              </b>
            </span>
          )}
        </div>
      )}

      <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
        Device Usage measures elapsed time between screen lock and unlock state
        changes. elapsed_device_on and elapsed_device_off are milliseconds. A
        positive on value means the device had been on or active for that long
        before the state changed; a positive off value means it had been locked
        or off for that long. It does not record app usage, foreground app name,
        unlock count, or current screen state directly.
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart
              data={data}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
              <XAxis
                dataKey="time"
                tickFormatter={tickFormatter}
                tick={{ fill: "#5f746b", fontSize: 11 }}
                minTickGap={60}
              />
              <YAxis
                tick={{ fill: "#5f746b", fontSize: 11 }}
                width={48}
                tickFormatter={(value) => fmt(Number(value), 1)}
              />
              <Tooltip
                labelFormatter={(value) => new Date(value as number).toLocaleString()}
                formatter={(value: unknown, name: unknown, item: unknown) => {
                  const payload = (item as { payload?: UsagePoint }).payload;
                  const ms =
                    name === "onMinutes" ? payload?.onMs ?? 0 : payload?.offMs ?? 0;
                  return [
                    `${formatDuration(ms)} (${fmt(Number(value), 2)} min)`,
                    name === "onMinutes" ? "Device on" : "Device off",
                  ];
                }}
                contentStyle={{
                  background: "#fffdf8",
                  border: "1px solid rgba(48,67,54,0.14)",
                  borderRadius: 10,
                }}
                labelStyle={{ color: "#5f746b" }}
                itemStyle={{ color: "#193229" }}
              />
              <Bar dataKey="onMinutes" fill="#9333ea" name="onMinutes" />
              <Bar dataKey="offMinutes" fill="#0d9488" name="offMinutes" />
            </BarChart>
          </ResponsiveContainer>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Total on time
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {formatDuration(totalOnMs)}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Total off time
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {formatDuration(totalOffMs)}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                On intervals
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {onEvents.toLocaleString()}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Off intervals
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {offEvents.toLocaleString()}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
