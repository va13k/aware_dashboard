import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { SensorConfig } from '../config/sensors'
import type { SensorRecord } from '../types'
import { min, max, fmt } from '../utils/stats'

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
  const lastVal = values.length ? values[values.length - 1] : null
  const spanMs = data.length > 1
    ? (data[data.length - 1].time - data[0].time) * 1000
    : 0
  const tickFormatter = makeTickFormatter(spanMs)

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: config.color }} />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">{config.label}</h3>
        {config.unit && (
          <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
            {config.unit}
          </span>
        )}
      </div>

      {values.length > 0 && (
        <div className="flex items-center gap-3 mb-3 text-[11px] text-sage">
          <span><b className="text-ink">{values.length}</b> pts</span>
          <span>last <b className="text-ink">{fmt(lastVal!)}</b></span>
          <span>↓ <b className="text-ink">{fmt(min(values))}</b></span>
          <span>↑ <b className="text-ink">{fmt(max(values))}</b></span>
        </div>
      )}

      {loading ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-40 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
            <XAxis
              dataKey="time"
              tickFormatter={tickFormatter}
              tick={{ fill: '#5f746b', fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis tick={{ fill: '#5f746b', fontSize: 11 }} width={45} />
            <Tooltip
              labelFormatter={v => new Date((v as number) * 1000).toLocaleString()}
              contentStyle={{ background: '#fffdf8', border: '1px solid rgba(48,67,54,0.14)', borderRadius: 10 }}
              labelStyle={{ color: '#5f746b' }}
              itemStyle={{ color: '#193229' }}
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
