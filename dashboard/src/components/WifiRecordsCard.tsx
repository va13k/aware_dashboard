import type { SensorRecord } from "../types";

interface WifiRecordGroup {
  label: string;
  records: SensorRecord[];
}

interface Props {
  groups: WifiRecordGroup[];
  loading: boolean;
  className?: string;
  tableClassName?: string;
}

type WifiTableRow = SensorRecord & { source: string };

function valueText(value: unknown): string {
  if (value == null || value === "") return "-";
  return String(value);
}

function timeText(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function WifiRecordsCard({
  groups,
  loading,
  className = "",
  tableClassName = "max-h-56",
}: Props) {
  const rows = groups
    .flatMap((group) =>
      group.records.map(
        (record): WifiTableRow => ({ ...record, source: group.label }),
      ),
    )
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 30);
  const total = groups.reduce((sum, group) => sum + group.records.length, 0);
  const showSource = groups.filter((group) => group.records.length).length > 1;

  return (
    <div
      className={`bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5 ${className}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#8b5cf6]" />
        <h3 className="text-[13px] font-semibold text-ink">Wi-Fi</h3>
        {total > 0 && (
          <span className="text-[11px] text-sage ml-auto">
            {total.toLocaleString()} records
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !rows.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className={`overflow-auto ${tableClassName}`}>
          <table className="w-full min-w-[560px] text-[12px] border-collapse">
            <thead>
              <tr className="text-sage border-b border-wire">
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Time
                </th>
                {showSource && (
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Source
                  </th>
                )}
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  SSID
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  BSSID
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  RSSI
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Frequency
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Security
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, index) => (
                <tr
                  key={`${r.source}:${r.id ?? index}:${r.timestamp}`}
                  className="border-b border-wire/50"
                >
                  <td className="py-1 text-sage pr-4 whitespace-nowrap">
                    {timeText(r.timestamp)}
                  </td>
                  {showSource && (
                    <td className="py-1 text-sage pr-4 whitespace-nowrap">
                      {r.source}
                    </td>
                  )}
                  <td className="py-1 text-ink pr-4 whitespace-nowrap">
                    {valueText(r.ssid)}
                  </td>
                  <td className="py-1 text-ink pr-4 whitespace-nowrap">
                    {valueText(r.bssid ?? r.mac_address)}
                  </td>
                  <td className="py-1 text-ink pr-4 whitespace-nowrap">
                    {valueText(r.rssi)}
                  </td>
                  <td className="py-1 text-ink pr-4 whitespace-nowrap">
                    {valueText(r.frequency)}
                  </td>
                  <td className="py-1 text-ink whitespace-nowrap">
                    {valueText(r.security ?? r.label)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
