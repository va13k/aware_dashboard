import { useEffect, useState } from "react";
import ExportLink from "./ExportLink";
import PeriodPicker from "./PeriodPicker";
import type { ChosenPeriod, ExportPlatform } from "../types";

/**
 * Choosing what to download, then downloading it.
 *
 * Two questions, and only two: which platforms, and which period. Everything
 * else — one sensor or the whole study — was decided by the button that opened
 * this, so the dialog never has to ask about scope.
 *
 * The period is *required* rather than defaulted: a study-scale export with no
 * period is a multi-gigabyte download nobody meant to start. "All time" stays
 * available as something to click, not as what happens when nothing is clicked.
 *
 * Both counts and the size estimate follow the platform choice, so the figures
 * describe the archive about to be produced rather than everything that exists.
 */
export default function ExportDialog({
  title,
  subtitle,
  href,
  hasAndroid = true,
  hasIos = true,
  sensor = null,
  device = null,
  onClose,
}: {
  title: string;
  subtitle?: string;
  /** Builds the download URL once the two questions are answered. */
  href: (period: ChosenPeriod, platform: ExportPlatform) => string;
  hasAndroid?: boolean;
  hasIos?: boolean;
  sensor?: string | null;
  /** Narrows the count to one phone, for a device's own export. */
  device?: string | null;
  onClose: () => void;
}) {
  // A scope only one platform ever collected has nothing to choose between, so
  // it opens on that platform rather than on a control with one live option.
  const only: ExportPlatform | null =
    hasAndroid && hasIos ? null : hasAndroid ? "android" : "ios";
  const [platform, setPlatform] = useState<ExportPlatform>(only ?? "all");
  const [period, setPeriod] = useState<ChosenPeriod | null>(null);
  // Null while unknown, which is not the same as empty: a count that failed to
  // load must not be the reason a download cannot be started.
  const [count, setCount] = useState<number | null>(null);
  const empty = count === 0;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="my-auto flex max-h-[90vh] w-full max-w-3xl flex-col overflow-y-auto rounded-3xl border border-wire bg-card p-7 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[17px] font-bold text-ink">{title}</h2>
            {subtitle ? <p className="text-[12px] text-sage">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 cursor-pointer rounded-lg border border-wire bg-card-strong px-2.5 py-1 text-[13px] font-semibold text-sage transition-colors hover:border-teal hover:text-teal"
          >
            ✕
          </button>
        </div>

        {/* Asked only when there is something to choose. A device belongs to
            one platform, and a sensor only one side collects has one answer —
            in both cases three buttons with two dead ones is a worse control
            than no control. */}
        {hasAndroid && hasIos ? (
        <div className="mb-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-sage">
            Platforms
          </p>
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                { key: "all", label: "All platforms", enabled: hasAndroid && hasIos },
                { key: "android", label: "Android", enabled: hasAndroid },
                { key: "ios", label: "iPhone", enabled: hasIos },
              ] as const
            ).map((option) => (
              <button
                key={option.key}
                type="button"
                disabled={!option.enabled}
                title={
                  option.enabled ? undefined : "Nothing was collected on that platform"
                }
                onClick={() => {
                  setCount(null);
                  setPlatform(option.key);
                }}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors ${
                  !option.enabled
                    ? "cursor-not-allowed border-wire bg-card-strong text-sage/30"
                    : platform === option.key
                      ? "border-teal bg-teal-soft text-teal"
                      : "border-wire bg-card-strong text-sage hover:border-teal hover:text-teal"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        ) : null}

        <PeriodPicker
          value={period}
          onChange={(chosen) => {
            setCount(null);
            setPeriod(chosen);
          }}
          onCount={setCount}
          // `all` asks about both sides, so the count and size describe the
          // whole archive rather than one half of it.
          platform={platform === "all" ? null : platform}
          sensor={sensor}
          device={device}
        />

        <div className="mt-4 flex items-center justify-end gap-2 border-t border-wire pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-wire bg-card-strong px-3 py-1.5 text-[11px] font-semibold text-sage transition-colors hover:border-teal hover:text-teal"
          >
            Cancel
          </button>
          <ExportLink
            href={period ? href(period, platform) : ""}
            label="Download ZIP"
            title={
              !period
                ? "Choose a period first"
                : empty
                  ? "This period holds nothing for the chosen scope"
                  : `Download ${period.label}`
            }
            disabled={!period || empty}
          />
        </div>
      </div>
    </div>
  );
}
