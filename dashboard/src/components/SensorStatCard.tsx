import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  Legend, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { mean, median, fmt } from '../utils/stats'
import type { SensorConfig } from '../config/sensors'
import type { SensorRecord } from '../types'

interface Props {
  config: SensorConfig
  androidRecords: SensorRecord[]
  iosRecords: SensorRecord[]
  loading: boolean
}

function extract(config: SensorConfig, records: SensorRecord[]): number[] {
  return records.map(r => config.extract(r)).filter((v): v is number => v !== null)
}

export default function SensorStatCard({ config, androidRecords, iosRecords, loading }: Props) {
  const androidValues = extract(config, androidRecords)
  const iosValues = extract(config, iosRecords)

  const chartData = [
    ...(androidValues.length ? [{
      platform: 'Android',
      Mean: parseFloat(fmt(mean(androidValues))),
      Median: parseFloat(fmt(median(androidValues))),
    }] : []),
    ...(iosValues.length ? [{
      platform: 'iOS',
      Mean: parseFloat(fmt(mean(iosValues))),
      Median: parseFloat(fmt(median(iosValues))),
    }] : []),
  ]

  const hasData = chartData.length > 0

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
      </div>

      {loading ? (
        <div className="h-40 rounded-md shimmer" />
      ) : !hasData ? (
        <div className="h-40 flex items-center justify-center text-slate-500 text-[13px]">
          No data
        </div>
      ) : (
        <>
          <div className="flex gap-4 mb-3">
            {chartData.map(d => (
              <div key={d.platform} className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-[0.5px] text-slate-500">
                  {d.platform}
                </span>
                <div className="flex items-baseline gap-1">
                  <span className="text-[11px] text-slate-500">mean</span>
                  <span className="text-[18px] font-bold leading-none" style={{ color: config.color }}>
                    {d.Mean}
                  </span>
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-[11px] text-slate-500">median</span>
                  <span className="text-[18px] font-bold leading-none text-indigo-400">
                    {d.Median}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3347" />
              <XAxis dataKey="platform" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} width={45} />
              <Tooltip
                contentStyle={{ background: '#1a1f2e', border: '1px solid #2d3347', borderRadius: 6 }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
              <Bar dataKey="Mean" fill={config.color} radius={[3, 3, 0, 0]} />
              <Bar dataKey="Median" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  )
}
