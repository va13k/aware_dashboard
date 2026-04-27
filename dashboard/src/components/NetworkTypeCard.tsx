import type { SensorRecord } from '../types'

const NETWORK_TYPES: Record<number, string> = {
  0: 'Mobile',
  1: 'WiFi',
  2: 'Mobile MMS',
  3: 'Mobile SUPL',
  4: 'Mobile DUN',
  5: 'Mobile HiPri',
  6: 'WiMAX',
  7: 'Bluetooth',
  9: 'Ethernet',
}

const NETWORK_STATES: Record<number, string> = {
  0: 'Disconnected',
  1: 'Connecting',
  2: 'Connected',
  3: 'Disconnecting',
}

const STATE_COLORS: Record<number, string> = {
  0: 'text-red-600',
  1: 'text-amber-600',
  2: 'text-emerald-600',
  3: 'text-orange-600',
}

interface Props {
  records: SensorRecord[]
  loading: boolean
}

export default function NetworkTypeCard({ records, loading }: Props) {
  const rows = [...records]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 30)

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-sage" />
        <h3 className="text-[13px] font-semibold text-ink">Network Type</h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage ml-auto">{records.length} events</span>
        )}
      </div>

      {loading ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : !rows.length ? (
        <div className="h-40 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="overflow-auto max-h-40">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr className="text-sage border-b border-wire">
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">Time</th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">Type</th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">State</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const type = r.network_type as number
                const state = r.network_state as number
                return (
                  <tr key={r.id} className="border-b border-wire/50">
                    <td className="py-1 text-sage pr-4 whitespace-nowrap">
                      {new Date(r.timestamp * 1000).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </td>
                    <td className="py-1 text-ink pr-4">
                      {NETWORK_TYPES[type] ?? `Type ${type}`}
                    </td>
                    <td className={`py-1 font-medium ${STATE_COLORS[state] ?? 'text-sage'}`}>
                      {NETWORK_STATES[state] ?? `State ${state}`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
