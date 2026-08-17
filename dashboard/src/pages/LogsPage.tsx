import { useState } from "react";
import LogsPanel from "../components/LogsPanel";

/**
 * Study-wide client logs (`aware_log`) across every device, reached from the
 * Overview. A device page shows the same panel scoped to one device.
 */
export default function LogsPage() {
  const [platform, setPlatform] = useState<"android" | "ios">("android");

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

      <LogsPanel key={platform} platform={platform} />
    </div>
  );
}
