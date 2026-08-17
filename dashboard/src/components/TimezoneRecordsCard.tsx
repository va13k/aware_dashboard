import type { SensorRecord } from "../types";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

function valueText(value: unknown): string {
  if (value == null || value === "") return "-";
  return String(value);
}

function timeText(timestamp: number): string {
  return new Date(timestamp).toLocaleString();
}

export default function TimezoneRecordsCard({
  records,
  loading,
  exportHref,
}: Props) {
  const rows = [...records].sort((a, b) => b.timestamp - a.timestamp);
  const latest = rows[0] ?? null;
  const uniqueTimezones = Array.from(
    new Set(
      records
        .map((record) => valueText(record.timezone))
        .filter((timezone) => timezone !== "-"),
    ),
  );

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#14b8a6]" />
        <h3 className="text-[14px] font-semibold text-ink">Timezone</h3>
        {records.length > 0 && (
          <span className="text-[12px] text-sage ml-auto">
            {records.length.toLocaleString()} records
          </span>
        )}
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !latest ? (
        <div className="h-44 flex items-center justify-center text-sage text-[14px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Current timezone
            </div>
            <div className="mt-1 text-[14px] font-semibold text-ink wrap-break-word">
              {valueText(latest.timezone)}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
                Last received
              </div>
              <div className="mt-1 text-[13px] font-semibold text-ink">
                {timeText(latest.timestamp)}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
                Unique values
              </div>
              <div className="mt-1 text-[13px] font-semibold text-ink">
                {uniqueTimezones.length.toLocaleString()}
              </div>
            </div>
          </div>

          {uniqueTimezones.length > 0 && (
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
                Timezones
              </div>
              <div className="mt-2 flex flex-col gap-1.5">
                {uniqueTimezones.map((timezone) => (
                  <div
                    key={timezone}
                    className="rounded-lg border border-wire/70 bg-card px-2.5 py-1.5 text-[13px] font-semibold text-ink wrap-break-word"
                  >
                    {timezone}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
