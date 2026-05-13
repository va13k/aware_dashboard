import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorRecord } from "../types";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

interface SignalPoint {
  time: number;
  rssi: number;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function valueText(value: unknown): string {
  if (value == null || value === "") return "-";
  return String(value);
}

function rssiLabel(rssi: number): string {
  if (rssi >= -55) return "strong";
  if (rssi >= -80) return "medium";
  return "weak";
}

function makeTickFormatter(spanMs: number) {
  const multiDay = spanMs > 24 * 60 * 60 * 1000;
  return (ts: number) => {
    const date = new Date(ts);
    if (multiDay) {
      return (
        date.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " " +
        date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    }
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };
}

function timeText(timestamp: number): string {
  return new Date(timestamp).toLocaleString();
}

export default function BluetoothRecordsCard({
  records,
  loading,
  exportHref,
}: Props) {
  const rows = [...records].sort((a, b) => b.timestamp - a.timestamp).slice(0, 30);
  const data = records
    .map((record): SignalPoint | null => {
      const rssi = numberValue(record.bt_rssi ?? record.rssi);
      if (rssi == null) return null;
      return { time: record.timestamp, rssi };
    })
    .filter((point): point is SignalPoint => point != null)
    .sort((a, b) => a.time - b.time);

  const latest = data.length ? data[data.length - 1] : null;
  const uniqueDevices = new Set(
    records
      .map((record) => valueText(record.bt_address ?? record.address))
      .filter((address) => address !== "-"),
  );
  const scanSessions = new Set(
    records
      .map((record) => valueText(record.label))
      .filter((label) => label !== "-"),
  );
  const spanMs =
    data.length > 1 ? data[data.length - 1].time - data[0].time : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#06b6d4]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Bluetooth Signal
        </h3>
        <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
          dBm
        </span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {data.length > 0 && latest && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[11px] text-sage">
          <span>
            <b className="text-ink">{records.length.toLocaleString()}</b>{" "}
            discoveries
          </span>
          <span>
            latest <b className="text-ink">{latest.rssi}</b> dBm
          </span>
          <span>
            strength <b className="text-ink">{rssiLabel(latest.rssi)}</b>
          </span>
          <span>
            devices <b className="text-ink">{uniqueDevices.size}</b>
          </span>
          <span>
            scans <b className="text-ink">{scanSessions.size}</b>
          </span>
        </div>
      )}

      <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
        RSSI closer to 0 is stronger: about -40 is strong, -70 is medium,
        and -90 is weak. On iPhone, the identifier is a CoreBluetooth
        peripheral UUID, not the real Bluetooth MAC address. iOS scans BLE
        advertisements/services, not classic paired-device history, and filters
        may miss nearby devices.
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !data.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart
              data={data}
              margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
              <XAxis
                dataKey="time"
                tickFormatter={tickFormatter}
                tick={{ fill: "#5f746b", fontSize: 11 }}
                minTickGap={60}
              />
              <YAxis
                tick={{ fill: "#5f746b", fontSize: 11 }}
                width={45}
                domain={["dataMin - 5", "dataMax + 5"]}
              />
              <Tooltip
                labelFormatter={(value) => new Date(value as number).toLocaleString()}
                formatter={(value: unknown) => [
                  `${Number(value).toFixed(0)} dBm (${rssiLabel(Number(value))})`,
                  "RSSI",
                ]}
                contentStyle={{
                  background: "#fffdf8",
                  border: "1px solid rgba(48,67,54,0.14)",
                  borderRadius: 10,
                }}
                labelStyle={{ color: "#5f746b" }}
                itemStyle={{ color: "#193229" }}
              />
              <Line
                type="monotone"
                dataKey="rssi"
                stroke="#06b6d4"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>

          <div className="overflow-auto max-h-56">
            <table className="w-full min-w-[680px] text-[12px] border-collapse">
              <thead>
                <tr className="text-sage border-b border-wire">
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Time
                  </th>
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Name
                  </th>
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Identifier
                  </th>
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    RSSI
                  </th>
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Strength
                  </th>
                  <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                    Scan session
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const rssi = numberValue(row.bt_rssi ?? row.rssi);
                  return (
                    <tr
                      key={`${row.id ?? index}:${row.timestamp}:${valueText(row.bt_address ?? row.address)}`}
                      className="border-b border-wire/50"
                    >
                      <td className="py-1 text-sage pr-4 whitespace-nowrap">
                        {timeText(row.timestamp)}
                      </td>
                      <td className="py-1 text-ink pr-4 whitespace-nowrap">
                        {valueText(row.bt_name ?? row.name)}
                      </td>
                      <td className="py-1 text-ink pr-4 whitespace-nowrap">
                        {valueText(row.bt_address ?? row.address)}
                      </td>
                      <td className="py-1 text-ink pr-4 whitespace-nowrap">
                        {rssi == null ? "-" : `${rssi} dBm`}
                      </td>
                      <td className="py-1 text-ink pr-4 whitespace-nowrap">
                        {rssi == null ? "-" : rssiLabel(rssi)}
                      </td>
                      <td className="py-1 text-ink whitespace-nowrap">
                        {valueText(row.label)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
