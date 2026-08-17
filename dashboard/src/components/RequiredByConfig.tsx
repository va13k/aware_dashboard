import type { SensorConfig } from "../config/sensors";

/**
 * Stands in for a sensor the deployed config requires but that has no data yet.
 *
 * It replaces the real (empty) card rather than overlaying a badge on it, so the
 * whole block reads as the flag - tinted orange, with "Required" and "No data"
 * stated in the body - and nothing overlaps the header controls.
 */
export function RequiredEmptyCard({
  config,
  className = "",
}: {
  config: SensorConfig;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col rounded-3xl border border-amber-300/70 bg-amber-50/70 p-5 shadow-card backdrop-blur-xl ${className}`.trim()}
    >
      <div className="mb-4 flex items-center gap-2">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: config.color }}
        />
        <h3 className="flex-1 text-[14px] font-semibold text-ink">
          {config.label}
        </h3>
        {config.unit ? (
          <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[12px] text-amber-700">
            {config.unit}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-1 py-10 text-center">
        <span className="text-[13px] font-semibold uppercase tracking-[0.5px] text-amber-700">
          Required
        </span>
        <span className="text-[14px] text-amber-700/80">No data yet</span>
      </div>
    </div>
  );
}

/**
 * The required settings the dashboard has no stream for, so the required view
 * never implies coverage it does not actually have.
 */
export function RequiredStreamNote({ settings }: { settings: string[] }) {
  if (settings.length === 0) return null;
  return (
    <p className="mt-4 rounded-xl border border-wire bg-card-strong/60 px-3 py-2 text-[12px] text-sage">
      No dashboard stream for {settings.length} required setting
      {settings.length === 1 ? "" : "s"}:{" "}
      <span className="font-mono text-ink">{settings.join(", ")}</span>
    </p>
  );
}
