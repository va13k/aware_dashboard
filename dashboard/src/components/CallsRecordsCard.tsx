import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorRecord } from "../types";
import { fmt, max, min } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function timeText(timestamp: number): string {
  return new Date(timestamp).toLocaleString();
}

function chartData(records: SensorRecord[]) {
  return records
    .map((record) => ({
      time: record.timestamp,
      duration: numberValue(record.call_duration),
    }))
    .filter(
      (row): row is { time: number; duration: number } => row.duration !== null,
    )
    .sort((a, b) => a.time - b.time);
}

export default function CallsRecordsCard({ records, loading, exportHref }: Props) {
  const sessionCount = new Set(
    records.map((record) => record.trace).filter((trace) => trace != null && trace !== ""),
  ).size;
  const data = chartData(records);
  const durations = data.map((row) => row.duration);
  const lastDuration = durations.length ? durations[durations.length - 1] : null;

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#f97316]" />
        <h3 className="text-[13px] font-semibold text-ink">Calls</h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage ml-auto">
            {records.length.toLocaleString()} records
          </span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !records.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          {durations.length > 0 && (
            <div className="flex items-center gap-3 text-[11px] text-sage">
              <span>
                last <b className="text-ink">{fmt(lastDuration!)} s</b>
              </span>
              <span>
                min <b className="text-ink">{fmt(min(durations))} s</b>
              </span>
              <span>
                max <b className="text-ink">{fmt(max(durations))} s</b>
              </span>
            </div>
          )}

          {data.length ? (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
                <XAxis
                  dataKey="time"
                  tickFormatter={(v) =>
                    new Date(v as number).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  }
                  tick={{ fill: "#5f746b", fontSize: 11 }}
                  minTickGap={60}
                />
                <YAxis tick={{ fill: "#5f746b", fontSize: 11 }} width={45} />
                <Tooltip
                  labelFormatter={(v) => timeText(v as number)}
                  formatter={(v: unknown) => [`${fmt(Number(v))} s`, "Duration"]}
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
                  dataKey="duration"
                  stroke="#f97316"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-sage text-[13px]">
              No duration data
            </div>
          )}

          <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
              Unique traces
            </div>
            <div className="mt-1 text-[18px] font-semibold text-ink">
              {sessionCount.toLocaleString()}
            </div>
          </div>

          <div className="rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
            Trace is a CallKit UUID for the call event/session, not a phone number.
          </div>
        </div>
      )}
    </div>
  );
}
