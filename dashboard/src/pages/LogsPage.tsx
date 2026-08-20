import { useEffect, useState } from "react";
import LogsPanel from "../components/LogsPanel";
import { fetchRefusals } from "../api/client";
import { absoluteTime } from "../utils/time";
import type { RefusalCounts } from "../types";

/**
 * Study-wide client logs (`aware_log`) across every device, reached from the
 * Overview. A device page shows the same panel scoped to one device.
 *
 * Writes the server turned away sit above the logs, because they are the same
 * kind of reading and the only place they appear: a refused write stores nothing,
 * so no device row, count or grid can carry it. Both platforms are listed at once,
 * each entry saying which it came from. The toggle belongs to the log table below
 * and moving the refusals with it would hide a finding behind a tab.
 */
export default function LogsPage() {
  const [platform, setPlatform] = useState<"android" | "ios">("android");
  const [refusals, setRefusals] = useState<RefusalCounts | null>(null);

  useEffect(() => {
    fetchRefusals()
      .then(setRefusals)
      .catch(() => setRefusals(null));
  }, []);

  // Flattened across platforms, so a refusal is never behind the tab that is not
  // selected. The platform rides on the entry instead.
  const refused = Object.entries(refusals?.platforms ?? {}).flatMap(
    ([name, entry]) =>
      entry.refusals.map((refusal) => ({
        ...refusal,
        platform: name === "android" ? "Android" : "iPhone",
      })),
  );

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-2xl border border-wire bg-card p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[21px] font-bold text-ink">Client Logs</h1>
            <p className="mt-1 text-[13px] text-sage">
              Operation logs reported by every device. Filter by type, window or
              text, and download the filtered set.
            </p>
          </div>
          <div className="flex gap-1 rounded-xl border border-wire bg-card-strong p-1">
            {(["android", "ios"] as const).map((option) => (
              <button
                key={option}
                onClick={() => setPlatform(option)}
                className={`rounded-lg px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.4px] transition-colors ${
                  platform === option
                    ? "bg-card text-teal shadow-card"
                    : "text-sage hover:text-teal"
                }`}
              >
                {option === "android" ? "Android" : "iPhone"}
              </button>
            ))}
          </div>
        </div>
      </section>

      {refusals && refused.length > 0 ? (
        <section className="rounded-2xl border border-short/40 bg-short/10 p-5 shadow-card">
          <h2 className="text-[15px] font-bold text-short">
            {refusals.attempts.toLocaleString()}{" "}
            {refusals.attempts === 1 ? "write was" : "writes were"} refused at
            ingest
            {refusals.devices > 0
              ? `, from ${refusals.devices.toLocaleString()} ${
                  refusals.devices === 1 ? "device" : "devices"
                }`
              : ""}
          </h2>
          <ul className="mt-3 space-y-1 text-[13px] text-sage">
            {refused.map((refusal) => (
              <li key={`${refusal.platform}-${refusal.device_id}-${refusal.reason}`}>
                <span className="font-semibold text-ink">
                  {refusal.platform}
                </span>
                {" · "}
                <span className="font-semibold text-ink">
                  {refusal.device_id || "no device id"}
                </span>{" "}
                — {refusal.explanation}. {refusal.attempts.toLocaleString()}{" "}
                {refusal.attempts === 1 ? "attempt" : "attempts"},{" "}
                {refusal.rows_refused.toLocaleString()}{" "}
                {refusal.rows_refused === 1 ? "row" : "rows"}
                {refusal.last_table ? `, last into ${refusal.last_table}` : ""}
                {". "}
                {/* Both ends, because one attempt this afternoon and a fortnight
                    of retries need different answers. */}
                First {absoluteTime(refusal.first_seen)}, last{" "}
                {absoluteTime(refusal.last_seen)}.
              </li>
            ))}
          </ul>
          <div className="mt-3 space-y-2 text-[13px] text-sage">
            <p>
              Nothing was stored. A write is refused when the device holds no
              enrolment window the study log put there, or when the request named
              no device at all — so these attempts appear nowhere else, because
              every other number the dashboard shows is read from rows that
              arrived.
            </p>
            <p>
              A device here is worth identifying rather than dismissing: a phone
              reinstalled or re-enrolled outside the study log looks exactly like
              one that never joined. Once it has a window, the next batch it
              sends is accepted and these counts stop rising.
            </p>
            <p>
              The counts are cumulative and nothing clears them, so an entry
              whose last attempt is old has already stopped.
            </p>
          </div>
        </section>
      ) : null}

      <LogsPanel key={platform} platform={platform} />
    </div>
  );
}
