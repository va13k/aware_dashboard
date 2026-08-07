import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { SensorConfig } from "../config/sensors";
import type { SeriesBucket } from "../types";
import { fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  config: SensorConfig;
  buckets: SeriesBucket[];
  loading: boolean;
  exportHref?: string;
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

interface Row {
  t: number;
  avg: number | null;
  band: [number, number] | undefined;
  n: number;
}

function SeriesTooltip({
  active,
  payload,
  unit,
}: {
  active?: boolean;
  payload?: { payload: Row }[];
  unit?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const suffix = unit ? ` ${unit}` : "";
  return (
    <div className="rounded-[10px] border border-[rgba(48,67,54,0.14)] bg-[#fffdf8] px-3 py-2 text-[11px]">
      <div className="text-sage">{new Date(row.t).toLocaleString()}</div>
      {row.avg != null ? (
        <div className="mt-0.5 text-ink">
          avg <b>{fmt(row.avg)}</b>
          {suffix}
        </div>
      ) : null}
      {row.band ? (
        <div className="text-sage">
          {fmt(row.band[0])} – {fmt(row.band[1])}
          {suffix}
        </div>
      ) : null}
      <div className="text-sage">
        <b className="text-ink">{row.n.toLocaleString()}</b> samples
      </div>
    </div>
  );
}

export default function SeriesChart({
  config,
  buckets,
  loading,
  exportHref,
}: Props) {
  const data: Row[] = buckets.map((b) => ({
    t: b.t,
    avg: b.avg,
    band:
      b.lo != null && b.hi != null ? ([b.lo, b.hi] as [number, number]) : undefined,
    n: b.n,
  }));

  const avgs = data
    .map((d) => d.avg)
    .filter((v): v is number => v != null);
  const los = buckets.map((b) => b.lo).filter((v): v is number => v != null);
  const his = buckets.map((b) => b.hi).filter((v): v is number => v != null);
  const totalSamples = buckets.reduce((sum, b) => sum + b.n, 0);
  const lastAvg = avgs.length ? avgs[avgs.length - 1] : null;
  const spanMs = data.length > 1 ? data[data.length - 1].t - data[0].t : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
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
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {data.length > 0 && (
        <div className="flex items-center gap-3 mb-3 text-[11px] text-sage">
          <span>
            <b className="text-ink">{data.length}</b> buckets
          </span>
          <span>
            <b className="text-ink">{totalSamples.toLocaleString()}</b> samples
          </span>
          {lastAvg != null && (
            <>
              <span>
                last <b className="text-ink">{fmt(lastAvg)}</b>
              </span>
              {los.length > 0 && (
                <span>
                  ↓ <b className="text-ink">{fmt(Math.min(...los))}</b>
                </span>
              )}
              {his.length > 0 && (
                <span>
                  ↑ <b className="text-ink">{fmt(Math.max(...his))}</b>
                </span>
              )}
            </>
          )}
        </div>
      )}

      {config.note && (
        <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
          {config.note}
        </div>
      )}

      {loading ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-40 flex items-center justify-center text-sage text-[13px]">
          No data in this range
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={tickFormatter}
              tick={{ fill: "#5f746b", fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis tick={{ fill: "#5f746b", fontSize: 11 }} width={45} />
            <Tooltip content={<SeriesTooltip unit={config.unit} />} />
            <Area
              type="monotone"
              dataKey="band"
              stroke="none"
              fill={config.color}
              fillOpacity={0.15}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="avg"
              stroke={config.color}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
