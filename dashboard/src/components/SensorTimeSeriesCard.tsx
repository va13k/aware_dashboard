import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { SensorConfig } from '../config/sensors'
import type { SensorRecord } from '../types'
import { mean, median, fmt } from '../utils/stats'

interface Props {
  config: SensorConfig
  records: SensorRecord[]
  loading: boolean
}

function makeTickFormatter(spanMs: number) {
  const multiDay = spanMs > 24 * 60 * 60 * 1000
  return (ts: number) => {
    const d = new Date(ts * 1000)
    if (multiDay) {
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
        + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
}

export default function SensorTimeSeriesCard({ config, records, loading }: Props) {
  const data = records
    .map(r => ({ time: r.timestamp, value: config.extract(r) }))
    .filter((r): r is { time: number; value: number } => r.value !== null)
    .sort((a, b) => a.time - b.time)

  const values = data.map(d => d.value)
  const spanMs = data.length > 1
    ? (data[data.length - 1].time - data[0].time) * 1000
    : 0
  const tickFormatter = makeTickFormatter(spanMs)

  return (
    <div className="bg-[#1a1f2e] border border-[#2d3347] rounded-[10px] p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: config.color }} />
        <h3 className="text-[13px] font-semibold flex-1">{config.label}</h3>
        {config.unit && (
          <span className="text-[11px] text-slate-500 bg-[#2d3347] px-1.5 py-0.5 rounded">
            {config.unit}
          </span>
        )}
        {values.length > 0 && (
          <span className="text-[11px] text-slate-500 ml-auto">
            mean <b className="text-slate-400">{fmt(mean(values))}</b>
            {' · '}
            median <b className="text-slate-400">{fmt(median(values))}</b>
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-40 rounded-md shimmer" />
      ) : !data.length ? (
        <div className="h-40 flex items-center justify-center text-slate-500 text-[13px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3347" />
            <XAxis
              dataKey="time"
              tickFormatter={tickFormatter}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} width={45} />
            <Tooltip
              labelFormatter={v => new Date((v as number) * 1000).toLocaleString()}
              contentStyle={{ background: '#1a1f2e', border: '1px solid #2d3347', borderRadius: 6 }}
              labelStyle={{ color: '#94a3b8' }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={config.color}
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
