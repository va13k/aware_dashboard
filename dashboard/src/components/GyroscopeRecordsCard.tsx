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
import { fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

interface AxisPoint {
  time: number;
  x: number;
  y: number;
  z: number;
  magnitude: number;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function axisValue(record: SensorRecord, rawKey: string, iosKey: string): number | null {
  return numberValue(record[rawKey]) ?? numberValue(record[iosKey]);
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

export default function GyroscopeRecordsCard({
  records,
  loading,
  exportHref,
}: Props) {
  const data = records
    .map((record): AxisPoint | null => {
      const x = axisValue(record, "double_values_0", "x");
      const y = axisValue(record, "double_values_1", "y");
      const z = axisValue(record, "double_values_2", "z");
      if (x == null || y == null || z == null) return null;
      return {
        time: record.timestamp,
        x,
        y,
        z,
        magnitude: Math.sqrt(x * x + y * y + z * z),
      };
    })
    .filter((point): point is AxisPoint => point != null)
    .sort((a, b) => a.time - b.time);

  const last = data.length ? data[data.length - 1] : null;
  const spanMs =
    data.length > 1 ? data[data.length - 1].time - data[0].time : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#ef4444]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Gyroscope
        </h3>
        <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
          rad/s
        </span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {data.length > 0 && last && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[11px] text-sage">
          <span>
            <b className="text-ink">{data.length}</b> pts
          </span>
          <span>
            x <b className="text-ink">{fmt(last.x, 3)}</b>
          </span>
          <span>
            y <b className="text-ink">{fmt(last.y, 3)}</b>
          </span>
          <span>
            z <b className="text-ink">{fmt(last.z, 3)}</b>
          </span>
          <span>
            |ω| <b className="text-ink">{fmt(last.magnitude, 3)}</b>
          </span>
        </div>
      )}

      <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
        Gyroscope values are angular velocity around the x, y, and z axes.
        Values near 0 mean the phone is not rotating. Positive and negative
        values indicate rotation direction; larger absolute values mean faster
        rotation.
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart
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
              width={45}
              tickFormatter={(value) => fmt(Number(value), 1)}
            />
            <Tooltip
              labelFormatter={(value) => new Date(value as number).toLocaleString()}
              formatter={(value: unknown, name: unknown) => [
                `${fmt(Number(value), 3)} rad/s`,
                String(name).toUpperCase(),
              ]}
              contentStyle={{
                background: "#fffdf8",
                border: "1px solid rgba(48,67,54,0.14)",
                borderRadius: 10,
              }}
              labelStyle={{ color: "#5f746b" }}
              itemStyle={{ color: "#193229" }}
            />
            <Line type="monotone" dataKey="x" stroke="#f97316" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="y" stroke="#2563eb" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="z" stroke="#16a34a" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
