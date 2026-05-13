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
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

const USER_APP_COLOR = "#10b981";
const SYSTEM_APP_COLOR = "#94a3b8";

export default function ApplicationsCard({ records, loading, exportHref }: Props) {
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

  const data = Object.entries(counts)
    .map(([name, { count, isSystem }]) => ({ name, count, isSystem }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#10b981]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">App Usage</h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage">{records.length} events</span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {records.length > 0 && (
        <div className="flex items-center gap-3 mb-3 text-[11px] text-sage">
          <span>
            <span className="inline-block w-2 h-2 rounded-full bg-[#10b981] mr-1" />
            user app
          </span>
          <span>
            <span className="inline-block w-2 h-2 rounded-full bg-[#94a3b8] mr-1" />
            system app
          </span>
        </div>
      )}

      {loading ? (
        <div className="h-52 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-52 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer
          width="100%"
          height={Math.max(160, data.length * 28)}
        >
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
          >
            <XAxis type="number" tick={{ fill: "#5f746b", fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fill: "#5f746b", fontSize: 11 }}
              width={140}
              tickFormatter={(v) => (v.length > 20 ? v.slice(0, 19) + "…" : v)}
            />
            <Tooltip
              contentStyle={{
                background: "#fffdf8",
                border: "1px solid rgba(48,67,54,0.14)",
                borderRadius: 10,
              }}
              labelStyle={{ color: "#5f746b" }}
              itemStyle={{ color: "#193229" }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {data.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={entry.isSystem ? SYSTEM_APP_COLOR : USER_APP_COLOR}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
