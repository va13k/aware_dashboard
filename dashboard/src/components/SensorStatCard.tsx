import type { SensorConfig } from '../config/sensors'
import type { SensorRecord } from '../types'
import { min, max, fmt } from '../utils/stats'

interface Props {
  config: SensorConfig
  androidRecords: SensorRecord[]
  iosRecords: SensorRecord[]
  loading: boolean
}

interface PlatformStats {
  count: number
  last: number
  min: number
  max: number
}

function platformStats(config: SensorConfig, records: SensorRecord[]): PlatformStats | null {
  const pairs = records
    .map(r => ({ ts: r.timestamp, v: config.extract(r) }))
    .filter((x): x is { ts: number; v: number } => x.v !== null)
  if (!pairs.length) return null
  const values = pairs.map(p => p.v)
  const latest = pairs.reduce((a, b) => (b.ts > a.ts ? b : a))
  return { count: values.length, last: latest.v, min: min(values), max: max(values) }
}

interface StatItemProps {
  label: string
  children: React.ReactNode
}

function StatItem({ label, children }: StatItemProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-[0.5px] text-sage">{label}</span>
      <span className="text-[15px] font-bold leading-none text-ink">{children}</span>
    </div>
  )
}

export default function SensorStatCard({ config, androidRecords, iosRecords, loading }: Props) {
  const android = platformStats(config, androidRecords)
  const ios = platformStats(config, iosRecords)
  const hasData = android || ios

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: config.color }} />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">{config.label}</h3>
        {config.unit && (
          <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
            {config.unit}
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-28 rounded-xl shimmer" />
      ) : !hasData ? (
        <div className="h-28 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="flex gap-6">
          {android && (
            <div className="flex-1">
              <p className="text-[10px] uppercase tracking-[0.5px] text-sage mb-3">Android</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <StatItem label="records">{android.count.toLocaleString()}</StatItem>
                <StatItem label="last">
                  <span style={{ color: config.color }}>{fmt(android.last)}</span>
                </StatItem>
                <StatItem label="min">{fmt(android.min)}</StatItem>
                <StatItem label="max">{fmt(android.max)}</StatItem>
              </div>
            </div>
          )}
          {android && ios && <div className="w-px bg-wire self-stretch" />}
          {ios && (
            <div className="flex-1">
              <p className="text-[10px] uppercase tracking-[0.5px] text-sage mb-3">iOS</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <StatItem label="records">{ios.count.toLocaleString()}</StatItem>
                <StatItem label="last">
                  <span style={{ color: config.color }}>{fmt(ios.last)}</span>
                </StatItem>
                <StatItem label="min">{fmt(ios.min)}</StatItem>
                <StatItem label="max">{fmt(ios.max)}</StatItem>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
