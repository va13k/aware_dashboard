import type { SensorConfig } from "../config/sensors";
import { relativeAge } from "../utils/time";

/**
 * A lightweight sensor summary in the device grid: name, total record count and
 * last-seen, with nothing fetched until the user opens it. Clicking opens the
 * chart on demand.
 */
export default function SensorTile({
  config,
  count,
  lastSeen,
  required,
  onOpen,
}: {
  config: SensorConfig;
  count: number;
  lastSeen: number | null;
  /** Required by the config but with no data yet - flagged orange. */
  required: boolean;
  onOpen: () => void;
}) {
  const empty = count === 0;
  const flagged = required && empty;

  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex h-full min-w-0 cursor-pointer flex-col rounded-2xl border p-4 text-left shadow-card transition-colors ${
        flagged
          ? "border-amber-300/70 bg-amber-50/70 hover:bg-amber-50"
          : "border-wire bg-card hover:border-teal hover:bg-teal-soft/40"
      }`}
    >
      <div className="mb-3 flex items-center gap-2">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: config.color }}
        />
        <h3 className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink">
          {config.label}
        </h3>
        {config.unit ? (
          <span className="shrink-0 rounded-md bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 text-[11px] text-sage">
            {config.unit}
          </span>
        ) : null}
      </div>

      <div className="mt-auto flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div
            className={`text-[22px] font-bold leading-none ${
              flagged ? "text-amber-700" : empty ? "text-sage" : "text-ink"
            }`}
          >
            {count.toLocaleString()}
          </div>
          <div className="mt-1 text-[11px] text-sage">
            {flagged ? "required · no data" : "records"}
          </div>
        </div>
        <div className="shrink-0 text-right text-[11px] text-sage">
          {lastSeen != null ? relativeAge(lastSeen) : "—"}
        </div>
      </div>
    </button>
  );
}
