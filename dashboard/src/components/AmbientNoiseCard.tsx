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
  className?: string;
}

const COLOR_DB = "#0ea5e9";
const COLOR_FREQ = "#8b5cf6";

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
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

function SubcardShell({
  color,
  title,
  unit,
  children,
}: {
  color: string;
  title: string;
  unit?: string;
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
        {unit && <span className="text-[10px] text-sage">{unit}</span>}
      </div>
      {children}
    </div>
  );
}

function MetricChart({
  data,
  color,
  unit,
  tickFormatter,
  valueLabel,
}: {
  data: { time: number; value: number }[];
  color: string;
  unit: string;
  tickFormatter: (ts: number) => string;
  valueLabel: string;
}) {
  const values = data.map((d) => d.value);
  const lastVal = values[values.length - 1] ?? null;

  if (!data.length) {
    return (
      <div className="h-[148px] flex items-center justify-center text-sage text-[12px]">
        No data
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-3 mb-2 text-[10px] text-sage">
        <span>
          last <b className="text-ink">{fmt(lastVal!, 1)}</b> {unit}
        </span>
        <span>
          ↓ <b className="text-ink">{fmt(min(values), 1)}</b>
        </span>
        <span>
          ↑ <b className="text-ink">{fmt(max(values), 1)}</b>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
          <XAxis
            dataKey="time"
            tickFormatter={tickFormatter}
            tick={{ fill: "#5f746b", fontSize: 10 }}
            minTickGap={40}
          />
          <YAxis tick={{ fill: "#5f746b", fontSize: 10 }} width={44} />
          <Tooltip
            labelFormatter={(v) => new Date(v as number).toLocaleString()}
            formatter={(v: unknown) => [
              `${fmt(Number(v), 2)} ${unit}`,
              valueLabel,
            ]}
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
            stroke={color}
            dot={false}
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export default function AmbientNoiseCard({
  records,
  loading,
  exportHref,
  className = "",
}: Props) {
  const sorted = [...records].sort((a, b) => a.timestamp - b.timestamp);

  const dbData = sorted
    .map((r) => ({
      time: r.timestamp,
      value: numberValue(r.double_decibels) ?? numberValue(r.decibels),
    }))
    .filter((r): r is { time: number; value: number } => r.value !== null);

  const freqData = sorted
    .map((r) => ({
      time: r.timestamp,
      value: numberValue(r.double_frequency) ?? numberValue(r.frequency),
    }))
    .filter((r): r is { time: number; value: number } => r.value !== null);

  const silentCount = records.filter(
    (r) => numberValue(r.is_silent) === 1,
  ).length;
  const silenceRatio =
    records.length > 0
      ? Math.round((silentCount / records.length) * 100)
      : null;

  const spanMs =
    sorted.length > 1
      ? sorted[sorted.length - 1].timestamp - sorted[0].timestamp
      : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: COLOR_DB }}
        />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Ambient Noise
        </h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage">
            {records.length.toLocaleString()} records
          </span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {loading ? (
        <div className="h-72 rounded-xl shimmer" />
      ) : !records.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 min-[760px]:grid-cols-2">
            <SubcardShell color={COLOR_DB} title="Sound Level" unit="dB">
              <MetricChart
                data={dbData}
                color={COLOR_DB}
                unit="dB"
                tickFormatter={tickFormatter}
                valueLabel="Decibels"
              />
            </SubcardShell>

            <SubcardShell color={COLOR_FREQ} title="Frequency" unit="Hz">
              <MetricChart
                data={freqData}
                color={COLOR_FREQ}
                unit="Hz"
                tickFormatter={tickFormatter}
                valueLabel="Frequency"
              />
            </SubcardShell>
          </div>

          {silenceRatio != null && (
            <div className="rounded-2xl border border-wire bg-card-strong/70 px-4 py-3 flex items-center gap-4 text-[11px]">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: "#64748b" }}
              />
              <span className="text-ink font-semibold">Silence</span>
              <span className="text-sage">
                <b className="text-ink">{silenceRatio}%</b> of samples silent ·{" "}
                {silentCount.toLocaleString()} / {records.length.toLocaleString()} records
              </span>
            </div>
          )}

          <div className="rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage space-y-1">
            <p>
              Recorded by the AWARE Ambient Noise plugin using short microphone
              bursts. <b className="text-ink">double_decibels</b> is the
              measured dB SPL level; <b className="text-ink">double_frequency</b>{" "}
              is the dominant frequency of the sample in Hz;{" "}
              <b className="text-ink">double_rms</b> is the raw RMS amplitude.
            </p>
            <p>
              <b className="text-ink">is_silent</b> is 1 when the dB level is
              below <b className="text-ink">double_silence_threshold</b>,
              otherwise 0. No raw audio is stored — only derived metrics.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
