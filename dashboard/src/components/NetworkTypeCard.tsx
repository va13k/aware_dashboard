import type { SensorRecord } from "../types";

const NETWORK_TYPES: Record<number, string> = {
  0: "Mobile",
  1: "WiFi",
  2: "Mobile MMS",
  3: "Mobile SUPL",
  4: "Mobile DUN",
  5: "Mobile HiPri",
  6: "WiMAX",
  7: "Bluetooth",
  9: "Ethernet",
};

const IOS_NETWORK_TYPES: Record<number, string> = {
  0: "Not reachable",
  1: "Wi-Fi",
  4: "Cellular",
};

const NETWORK_STATES: Record<number, string> = {
  0: "Disconnected",
  1: "Connecting",
  2: "Connected",
  3: "Disconnecting",
};

const IOS_NETWORK_STATES: Record<number, string> = {
  0: "Not reachable",
  1: "Connected",
};

const STATE_COLORS: Record<number, string> = {
  0: "text-red-600",
  1: "text-amber-600",
  2: "text-emerald-600",
  3: "text-orange-600",
};

const IOS_STATE_COLORS: Record<number, string> = {
  0: "text-red-600",
  1: "text-emerald-600",
};

interface Props {
  records: SensorRecord[];
  loading: boolean;
  platform?: "android" | "ios";
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function textValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return String(value);
}

function typeLabel(
  type: number | null,
  subtype: string,
  platform?: "android" | "ios",
) {
  if (type == null) return subtype || "-";
  if (platform === "ios") return IOS_NETWORK_TYPES[type] ?? `Type ${type}`;
  return subtype || NETWORK_TYPES[type] || `Type ${type}`;
}

function stateLabel(state: number | null, platform?: "android" | "ios") {
  if (state == null) return "-";
  if (platform === "ios") return IOS_NETWORK_STATES[state] ?? `State ${state}`;
  return NETWORK_STATES[state] ?? `State ${state}`;
}

function stateColor(state: number | null, platform?: "android" | "ios") {
  if (state == null) return "text-sage";
  if (platform === "ios") return IOS_STATE_COLORS[state] ?? "text-sage";
  return STATE_COLORS[state] ?? "text-sage";
}

export default function NetworkTypeCard({ records, loading, platform }: Props) {
  const rows = [...records]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 30);
  const latest = rows[0] ?? null;
  const latestType = latest ? numberValue(latest.network_type) : null;
  const latestSubtype = latest ? textValue(latest.network_subtype) : "";
  const latestState = latest ? numberValue(latest.network_state) : null;

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-sage" />
        <h3 className="text-[13px] font-semibold text-ink">
          {platform === "ios" ? "Network Reachability" : "Network Type"}
        </h3>
        {records.length > 0 && (
          <span className="text-[11px] text-sage ml-auto">
            {records.length} events
          </span>
        )}
      </div>

      {latest && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[11px] text-sage">
          <span>
            current{" "}
            <b className="text-ink">
              {typeLabel(latestType, latestSubtype, platform)}
            </b>
          </span>
          <span>
            state{" "}
            <b className={stateColor(latestState, platform)}>
              {stateLabel(latestState, platform)}
            </b>
          </span>
        </div>
      )}

      {platform === "ios" && (
        <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
          iOS network data shows reachability only: Wi-Fi, cellular, or not
          reachable. It does not include SSID, BSSID, IP address, carrier,
          LTE/5G subtype, bandwidth, bytes, or per-app traffic. The client app
          checks reachability to github.com when the sensor starts, so rows may
          show a startup status rather than every later network change.
        </div>
      )}

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
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Time
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Type
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  Subtype
                </th>
                <th className="text-left pb-1.5 font-semibold text-[10px] uppercase tracking-[0.5px]">
                  State
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const type = numberValue(r.network_type);
                const subtype = textValue(r.network_subtype);
                const state = numberValue(r.network_state);
                return (
                  <tr key={r.id} className="border-b border-wire/50">
                    <td className="py-1 text-sage pr-4 whitespace-nowrap">
                      {new Date(r.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                    <td className="py-1 text-ink pr-4">
                      {typeLabel(type, subtype, platform)}
                    </td>
                    <td className="py-1 text-sage pr-4">{subtype || "-"}</td>
                    <td
                      className={`py-1 font-medium ${stateColor(state, platform)}`}
                    >
                      {stateLabel(state, platform)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
