import { useEffect, useState } from 'react'
import { fetchDevices, fetchSensor } from '../api/client'
import { SENSOR_CONFIGS } from '../config/sensors'
import SensorTimeSeriesCard from '../components/SensorTimeSeriesCard'
import NetworkTypeCard from '../components/NetworkTypeCard'
import type { Device, DevicesResponse, SensorRecord } from '../types'

function deviceLabel(d: Device): string {
  if (d.platform === 'android') {
    const name = [d.manufacturer, d.model].filter(Boolean).join(' ')
    return `Android · ${name || d.device_id.slice(0, 12)}`
  }
  return `iOS · ${d.device_id.slice(0, 16)}`
}

export default function DevicePage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null)
  const [selected, setSelected] = useState<Device | null>(null)
  const [sensorData, setSensorData] = useState<Record<string, SensorRecord[]>>({})
  const [networkData, setNetworkData] = useState<SensorRecord[]>([])
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set())
  const [networkLoading, setNetworkLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDevices()
      .then(d => {
        setDevices(d)
        setSelected(d.android[0] ?? d.ios[0] ?? null)
      })
      .catch(e => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!selected) return
    let cancelled = false

    setSensorData({})
    setNetworkData([])
    setLoadingKeys(new Set(SENSOR_CONFIGS.map(s => s.key)))
    setNetworkLoading(true)

    for (const sensor of SENSOR_CONFIGS) {
      fetchSensor(selected.platform, selected.device_id, sensor.key)
        .then(records => {
          if (cancelled) return
          setSensorData(prev => ({ ...prev, [sensor.key]: records }))
        })
        .catch(() => {
          if (cancelled) return
          setSensorData(prev => ({ ...prev, [sensor.key]: [] }))
        })
        .finally(() => {
          if (cancelled) return
          setLoadingKeys(prev => {
            const next = new Set(prev)
            next.delete(sensor.key)
            return next
          })
        })
    }

    fetchSensor(selected.platform, selected.device_id, 'network')
      .then(records => { if (!cancelled) setNetworkData(records) })
      .catch(() => { if (!cancelled) setNetworkData([]) })
      .finally(() => { if (!cancelled) setNetworkLoading(false) })

    return () => { cancelled = true }
  }, [selected])

  if (error) return (
    <div className="mt-4 p-4 text-red-700 bg-red-50 border border-red-200 rounded-2xl">
      {error}
    </div>
  )

  if (!devices) return (
    <div className="text-sage py-8 text-center text-[13px]">Loading devices…</div>
  )

  const allDevices: Device[] = [...devices.android, ...devices.ios]

  return (
    <div>
      <div className="flex items-center gap-3 mb-1">
        <label htmlFor="device-select" className="text-[13px] text-sage font-medium">
          Device
        </label>
        <select
          id="device-select"
          value={selected?.device_id ?? ''}
          onChange={e => {
            const d = allDevices.find(d => d.device_id === e.target.value)
            if (d) setSelected(d)
          }}
          className="bg-card-strong border border-wire text-ink py-1.75 px-3 rounded-xl text-[13px] cursor-pointer min-w-65 focus:outline-2 focus:outline-teal"
        >
          {allDevices.map(d => (
            <option key={d.device_id} value={d.device_id}>
              {deviceLabel(d)}
            </option>
          ))}
        </select>
      </div>

      {selected && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4 mt-4">
          {SENSOR_CONFIGS.map(config => (
            <SensorTimeSeriesCard
              key={config.key}
              config={config}
              records={sensorData[config.key] ?? []}
              loading={loadingKeys.has(config.key)}
            />
          ))}
          <NetworkTypeCard records={networkData} loading={networkLoading} />
        </div>
      )}
    </div>
  )
}
