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
  className?: string;
  title?: string;
  color?: string;
  exportHref?: string;
}

interface LocationMetric {
  key: string;
  label: string;
  unit: string;
  color: string;
  fields: string[];
}

const LOCATION_METRICS: LocationMetric[] = [
  {
    key: "speed",
    label: "Speed",
    unit: "m/s",
    color: "#10b981",
    fields: ["double_speed", "speed"],
  },
  {
    key: "accuracy",
    label: "Accuracy",
    unit: "m",
    color: "#3b82f6",
    fields: ["accuracy", "horizontal_accuracy", "vertical_accuracy"],
  },
  {
    key: "altitude",
    label: "Altitude",
    unit: "m",
    color: "#8b5cf6",
    fields: ["double_altitude", "altitude"],
  },
  {
    key: "bearing",
    label: "Bearing",
    unit: "deg",
    color: "#f59e0b",
    fields: ["double_bearing", "bearing", "course"],
  },
  {
    key: "latitude",
    label: "Latitude",
    unit: "deg",
    color: "#06b6d4",
    fields: ["double_latitude", "latitude", "lat"],
  },
  {
    key: "longitude",
    label: "Longitude",
    unit: "deg",
    color: "#ef4444",
    fields: ["double_longitude", "longitude", "lon", "lng"],
  },
];

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function firstNumber(record: SensorRecord, fields: string[]): number | null {
  for (const field of fields) {
    const value = numberValue(record[field]);
    if (value != null) return value;
  }
  return null;
}

function makeChartData(records: SensorRecord[], metric: LocationMetric) {
  return records
    .map((record) => ({
      time: record.timestamp,
      value: firstNumber(record, metric.fields),
    }))
    .filter((row): row is { time: number; value: number } => row.value !== null)
    .sort((a, b) => a.time - b.time);
}

function LocationMetricChart({
  metric,
  records,
}: {
  metric: LocationMetric;
  records: SensorRecord[];
}) {
  const data = makeChartData(records, metric);
  const values = data.map((d) => d.value);
  const lastVal = values.length ? values[values.length - 1] : null;

  return (
    <div className="rounded-2xl border border-wire bg-card-strong/70 p-3 min-w-0">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: metric.color }}
        />
        <h4 className="text-[12px] font-semibold text-ink flex-1">
          {metric.label}
        </h4>
        <span className="text-[10px] text-sage">{metric.unit}</span>
      </div>

      {values.length ? (
        <>
          <div className="flex items-center gap-2 text-[10px] text-sage mb-2">
            <span>
              last <b className="text-ink">{fmt(lastVal!, 3)}</b>
            </span>
            <span>
              min <b className="text-ink">{fmt(min(values), 3)}</b>
            </span>
            <span>
              max <b className="text-ink">{fmt(max(values), 3)}</b>
            </span>
          </div>
          <ResponsiveContainer width="100%" height={120}>
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
                tick={{ fill: "#5f746b", fontSize: 10 }}
                minTickGap={40}
              />
              <YAxis tick={{ fill: "#5f746b", fontSize: 10 }} width={44} />
              <Tooltip
                labelFormatter={(v) => new Date(v as number).toLocaleString()}
                formatter={(v: unknown) => [fmt(Number(v), 5), metric.label]}
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
                stroke={metric.color}
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </>
      ) : (
        <div className="h-[148px] flex items-center justify-center text-sage text-[12px]">
          No data
        </div>
      )}
    </div>
  );
}

export default function LocationRecordsCard({
  records,
  loading,
  className = "",
  title = "Location",
  color = "#10b981",
  exportHref,
}: Props) {
  const sorted = [...records].sort((a, b) => b.timestamp - a.timestamp);
  const latest = sorted[0] ?? null;
  const showLocationAccuracyNote = title === "Location";

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: color }}
        />
        <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage ml-auto">
            {records.length.toLocaleString()} records
          </span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {loading ? (
        <div className="h-72 rounded-xl shimmer" />
      ) : !latest ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 min-[760px]:grid-cols-2">
            {LOCATION_METRICS.map((metric) => (
              <LocationMetricChart
                key={metric.key}
                metric={metric}
                records={records}
              />
            ))}
          </div>

          <div className="rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
            Bearing is the device course over ground from the iOS location fix,
            saved from location.course. It is movement direction, not compass
            heading or phone orientation: 0 deg is north, 90 deg east, 180 deg
            south, and 270 deg west. Values greater than or equal to 0 are valid
            course degrees; negative values, commonly -1, mean unknown or
            invalid course when the user is still, moving slowly, or course
            cannot be determined.
          </div>

          {showLocationAccuracyNote && (
            <div className="rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
              Accuracy is the estimated position radius in meters for the
              location fix. For example, 10 means the position is estimated
              within about 10 m, 150 within about 150 m, and 1000 within about
              1 km. Negative accuracy means invalid or unavailable accuracy.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
