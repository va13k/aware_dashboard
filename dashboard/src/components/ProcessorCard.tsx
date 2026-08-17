import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { SensorRecord } from "../types";
import { min, max, fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

interface DataPoint {
  time: number;
  user: number;
}

function numberValue(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
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

const COLOR = "#475569";

export default function ProcessorCard({ records, loading, exportHref }: Props) {
  const data: DataPoint[] = records
    .map((r) => {
      const user = numberValue(r.double_last_user);
      if (user == null) return null;
      return { time: r.timestamp, user };
    })
    .filter((d): d is DataPoint => d != null)
    .sort((a, b) => a.time - b.time);

  const userValues = data.map((d) => d.user);
  const last = data.length ? data[data.length - 1] : null;
  const spanMs =
    data.length > 1 ? data[data.length - 1].time - data[0].time : 0;
  const tickFormatter = makeTickFormatter(spanMs);
  const avg = userValues.length
    ? userValues.reduce((a, b) => a + b, 0) / userValues.length
    : null;

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: COLOR }}
        />
        <h3 className="text-[14px] font-semibold flex-1 text-ink">Processor</h3>
        <span className="text-[12px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
          %
        </span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {data.length > 0 && last != null && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[12px] text-sage">
          <span>
            <b className="text-ink">{data.length}</b> pts
          </span>
          <span>
            last{" "}
            <b className="text-ink" style={{ color: COLOR }}>
              {fmt(last.user, 1)}%
            </b>
          </span>
          <span>
            ↓ <b className="text-ink">{fmt(min(userValues), 1)}%</b>
          </span>
          <span>
            ↑ <b className="text-ink">{fmt(max(userValues), 1)}%</b>
          </span>
          {avg != null && (
            <span>
              avg <b className="text-ink">{fmt(avg, 1)}%</b>
            </span>
          )}
        </div>
      )}

      <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[12px] leading-snug text-sage space-y-1">
        <p>
          App CPU usage via Mach thread APIs — sum of non-idle thread time as a
          percentage. Only{" "}
          <code className="font-mono">double_last_user</code> is meaningful;
          system/load fields are always 0 in this implementation.
        </p>
        <p>
          Disabled on Android 7.0+ — the client stops the sensor on{" "}
          <code className="font-mono">Build.VERSION.SDK_INT &gt;= N</code>{" "}
          because Android restricted access to{" "}
          <code className="font-mono">/proc/stat</code>.
        </p>
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[14px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart
            data={data}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="proc-user-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={COLOR} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COLOR} stopOpacity={0.04} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
            <XAxis
              dataKey="time"
              tickFormatter={tickFormatter}
              tick={{ fill: "#5f746b", fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis
              tick={{ fill: "#5f746b", fontSize: 11 }}
              width={42}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
            />
            <ReferenceLine
              y={avg ?? 0}
              stroke={COLOR}
              strokeDasharray="4 3"
              strokeOpacity={0.45}
              strokeWidth={1}
            />
            <Tooltip
              labelFormatter={(v) => new Date(v as number).toLocaleString()}
              formatter={(value: unknown) => [
                `${fmt(Number(value), 1)}%`,
                "App CPU",
              ]}
              contentStyle={{
                background: "#fffdf8",
                border: "1px solid rgba(48,67,54,0.14)",
                borderRadius: 10,
              }}
              labelStyle={{ color: "#5f746b" }}
              itemStyle={{ color: "#193229" }}
            />
            <Area
              type="monotone"
              dataKey="user"
              stroke={COLOR}
              strokeWidth={2}
              fill="url(#proc-user-grad)"
              dot={false}
              activeDot={{ r: 3, fill: COLOR }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
