import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import type { SensorRecord } from '../types'

interface Props {
  records: SensorRecord[]
  loading: boolean
}

const ACTIVITY_COLORS: Record<string, string> = {
  stationary: '#94a3b8',
  walking:    '#22c55e',
  running:    '#f59e0b',
  cycling:    '#06b6d4',
  automotive: '#8b5cf6',
  unknown:    '#d1d5db',
}

export default function ActivityCard({ records, loading }: Props) {
  const counts: Record<string, number> = {}
  for (const r of records) {
    const type = ((r.activity_type as string | null) ?? 'unknown').toLowerCase()
    counts[type] = (counts[type] ?? 0) + 1
  }

  const data = Object.entries(counts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count)

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#22c55e]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">Activity</h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage">{records.length} events</span>
        )}
      </div>

      {loading ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-40 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <XAxis type="number" tick={{ fill: '#5f746b', fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="type"
              tick={{ fill: '#5f746b', fontSize: 11 }}
              width={76}
            />
            <Tooltip
              contentStyle={{ background: '#fffdf8', border: '1px solid rgba(48,67,54,0.14)', borderRadius: 10 }}
              labelStyle={{ color: '#5f746b' }}
              itemStyle={{ color: '#193229' }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {data.map(entry => (
                <Cell key={entry.type} fill={ACTIVITY_COLORS[entry.type] ?? '#94a3b8'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
