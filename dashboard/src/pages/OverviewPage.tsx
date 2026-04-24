import { useEffect, useState } from 'react'
import { fetchDevices, fetchSensor } from '../api/client'
import { SENSOR_CONFIGS } from '../config/sensors'
import SensorStatCard from '../components/SensorStatCard'
import type { SensorRecord } from '../types'

type SensorData = Record<string, { android: SensorRecord[]; ios: SensorRecord[] }>

export default function OverviewPage() {
  const [sensorData, setSensorData] = useState<SensorData>({})
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(
    new Set(SENSOR_CONFIGS.map(s => s.key)),
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const devices = await fetchDevices()

        for (const sensor of SENSOR_CONFIGS) {
          const [androidResults, iosResults] = await Promise.all([
            Promise.all(
              devices.android.map(d =>
                fetchSensor('android', d.device_id, sensor.key).catch(() => [] as SensorRecord[]),
              ),
            ),
            Promise.all(
              devices.ios.map(d =>
                fetchSensor('ios', d.device_id, sensor.key).catch(() => [] as SensorRecord[]),
              ),
            ),
          ])

          if (cancelled) return

          setSensorData(prev => ({
            ...prev,
            [sensor.key]: { android: androidResults.flat(), ios: iosResults.flat() },
          }))
          setLoadingKeys(prev => {
            const next = new Set(prev)
            next.delete(sensor.key)
            return next
          })
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }

    load()
    return () => { cancelled = true }
  }, [])

  if (error) return (
    <div className="mt-4 p-4 text-red-400 bg-red-950/50 border border-red-900 rounded-lg">
      {error}
    </div>
  )

  return (
    <div>
      <p className="text-slate-500 text-[13px]">
        Aggregate mean &amp; median across all devices, per sensor.
      </p>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4 mt-4">
        {SENSOR_CONFIGS.map(config => (
          <SensorStatCard
            key={config.key}
            config={config}
            androidRecords={sensorData[config.key]?.android ?? []}
            iosRecords={sensorData[config.key]?.ios ?? []}
            loading={loadingKeys.has(config.key)}
          />
        ))}
      </div>
    </div>
  )
}
