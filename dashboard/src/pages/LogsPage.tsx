import LogsPanel from "../components/LogsPanel";

/**
 * Study-wide client logs (`aware_log`) across every device, reached from the
 * Overview. A device page shows the same panel scoped to one device.
 */
export default function LogsPage() {
  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-2xl border border-wire bg-card p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[20px] font-bold text-ink">Client Logs</h1>
            <p className="mt-1 text-[12px] text-sage">
              Operation logs reported by every device (Android). Filter by type,
              window or text, and download the filtered set.
            </p>
          </div>
        </div>
      </section>

      <LogsPanel />
    </div>
  );
}
