import { useState } from "react";
import { fetchManifest } from "../api/client";
import { useLiveRefresh } from "../api/live";
import { SENSOR_CONFIGS } from "../config/sensors";
import type { ExcludedTotals, Manifest, SensorManifestEntry } from "../types";
import { absoluteDate, isoDateTime } from "../utils/time";

function studySpan(manifest: Manifest): {
  first: number | null;
  last: number | null;
} {
  let first: number | null = null;
  let last: number | null = null;
  for (const platform of Object.values(manifest.platforms)) {
    for (const entry of Object.values(platform.sensors)) {
      if (entry.first_timestamp != null)
        first =
          first == null
            ? entry.first_timestamp
            : Math.min(first, entry.first_timestamp);
      if (entry.last_timestamp != null)
        last =
          last == null
            ? entry.last_timestamp
            : Math.max(last, entry.last_timestamp);
    }
  }
  return { first, last };
}

function totalRecords(manifest: Manifest): number {
  return Object.values(manifest.platforms).reduce(
    (sum, p) =>
      sum + Object.values(p.sensors).reduce((s, e) => s + e.row_count, 0),
    0,
  );
}

/**
 * The devices and rows exclusion keeps out of every figure above.
 *
 * Read from each platform's own summary rather than summed over its sensors: one
 * excluded phone appears under as many sensors as it collected, and the study-wide
 * answer is how many phones and how many rows.
 */
function totalExcluded(manifest: Manifest): ExcludedTotals {
  return Object.values(manifest.platforms).reduce(
    (sum, p) => ({
      devices: sum.devices + (p.excluded?.devices ?? 0),
      records: sum.records + (p.excluded?.records ?? 0),
    }),
    { devices: 0, records: 0 },
  );
}

function downloadJson(manifest: Manifest) {
  const blob = new Blob([JSON.stringify(manifest, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `manifest_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const sensorConfigMap = Object.fromEntries(
  SENSOR_CONFIGS.map((s) => [s.key, s]),
);

interface SensorRowProps {
  name: string;
  entry: SensorManifestEntry;
  deviceCount: number;
}

function SensorRow({ name, entry, deviceCount }: SensorRowProps) {
  const [fieldsOpen, setFieldsOpen] = useState(false);
  const config = sensorConfigMap[name];
  const hasData = entry.row_count > 0 || entry.excluded_row_count > 0;

  return (
    <div
      className={`rounded-2xl border px-4 py-3 transition-colors ${
        hasData ? "border-wire bg-card" : "border-wire/50 bg-card/40"
      }`}
    >
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        {/* Name */}
        <div className="flex min-w-[160px] flex-1 items-center gap-2">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{
              background: config?.color ?? (hasData ? "#5f746b" : "#c4cfc8"),
            }}
          />
          <span
            className={`text-[14px] font-semibold ${hasData ? "text-ink" : "text-sage/60"}`}
          >
            {config?.label ?? name}
          </span>
          {!hasData && (
            <span className="rounded-md bg-wire/60 px-1.5 py-0.5 text-[11px] uppercase tracking-[0.4px] text-sage/50">
              no data
            </span>
          )}
        </div>

        {/* Stats */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Records
            </div>
            <div
              className={`text-[14px] font-bold ${hasData ? "text-ink" : "text-sage/40"}`}
            >
              {entry.row_count.toLocaleString()}
            </div>
            {entry.excluded_row_count > 0 ? (
              <div
                className="text-[11px] text-sage"
                title={`${entry.excluded_row_count.toLocaleString()} records from ${entry.excluded_devices} excluded device(s) are left out of exports`}
              >
                +{entry.excluded_row_count.toLocaleString()} excluded
              </div>
            ) : null}
          </div>

          <div className="text-right">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Devices
            </div>
            <div
              className={`text-[14px] font-bold ${hasData ? "text-ink" : "text-sage/40"}`}
            >
              {entry.devices_with_data}
              <span className="text-[12px] font-normal text-sage">
                {" "}
                / {deviceCount}
              </span>
            </div>
          </div>

          <div className="text-right">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              First sample
            </div>
            <div
              className={`text-[14px] font-bold ${hasData ? "text-ink" : "text-sage/40"}`}
            >
              {absoluteDate(entry.first_timestamp)}
            </div>
          </div>

          <div className="text-right">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Last sample
            </div>
            <div
              className={`text-[14px] font-bold ${hasData ? "text-ink" : "text-sage/40"}`}
            >
              {absoluteDate(entry.last_timestamp)}
            </div>
          </div>

          <div className="text-right">
            <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Fields
            </div>
            <button
              onClick={() => setFieldsOpen((o) => !o)}
              className="text-[14px] font-bold text-teal hover:underline cursor-pointer"
            >
              {entry.fields.length} {fieldsOpen ? "▲" : "▼"}
            </button>
          </div>
        </div>
      </div>

      {fieldsOpen && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-wire pt-3">
          {entry.fields.map((f) => (
            <span
              key={f}
              className="rounded-md bg-card-strong px-2 py-0.5 font-mono text-[11px] text-sage"
            >
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface PlatformSectionProps {
  platform: "android" | "ios";
  manifest: Manifest;
}

function PlatformSection({ platform, manifest }: PlatformSectionProps) {
  const data = manifest.platforms[platform];
  const label = platform === "android" ? "Android" : "iOS";
  const dotColor = platform === "android" ? "#22c55e" : "#3b82f6";
  const sensors = Object.entries(data.sensors).sort(
    ([, a], [, b]) => b.row_count - a.row_count,
  );
  const sensorsWithData = sensors.filter(([, e]) => e.row_count > 0).length;

  return (
    <section>
      <div className="mb-3 flex items-center gap-3 px-1">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: dotColor }}
        />
        <h2 className="text-[16px] font-bold text-ink">{label}</h2>
        <span className="text-[13px] text-sage">
          {data.device_count} {data.device_count === 1 ? "device" : "devices"} ·{" "}
          {sensorsWithData} of {sensors.length} sensors with data
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {sensors.map(([name, entry]) => (
          <SensorRow
            key={name}
            name={name}
            entry={entry}
            deviceCount={data.device_count}
          />
        ))}
      </div>
    </section>
  );
}

export default function ManifestPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetchManifest()
      .then((data) => {
        setManifest(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  };

  // Every row here is a record count, so an arrival changes one of them.
  useLiveRefresh(load);

  if (error)
    return (
      <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700">
        {error}
      </div>
    );

  const span = manifest ? studySpan(manifest) : null;
  const total = manifest ? totalRecords(manifest) : null;
  const excluded = manifest ? totalExcluded(manifest) : null;
  const allDevices = manifest
    ? manifest.platforms.android.device_count +
      manifest.platforms.ios.device_count
    : null;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <section className="rounded-2xl border border-wire bg-card p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[21px] font-bold text-ink">Study Manifest</h1>
            {manifest && (
              <p className="mt-1 text-[13px] text-sage">
                Generated {isoDateTime(manifest.generated_at)}
              </p>
            )}
          </div>
          {manifest && (
            <button
              onClick={() => downloadJson(manifest)}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-wire bg-card-strong px-4 text-[13px] font-semibold text-sage shadow-card transition-colors hover:border-teal hover:text-teal"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 2v8M5 7l3 3 3-3M3 13h10"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Download JSON
            </button>
          )}
        </div>

        {/* Summary stats */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            {
              label: "Android devices",
              value: manifest?.platforms.android.device_count ?? "—",
            },
            {
              label: "iOS devices",
              value: manifest?.platforms.ios.device_count ?? "—",
            },
            {
              label: "Records in exports",
              value: total != null ? total.toLocaleString() : "—",
            },
            {
              label: "Study span",
              value:
                span?.first != null && span?.last != null
                  ? `${absoluteDate(span.first)} – ${absoluteDate(span.last)}`
                  : "—",
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="rounded-xl border border-wire bg-card-strong/70 px-4 py-3"
            >
              <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
                {label}
              </div>
              <div className="mt-1 text-[16px] font-bold text-ink">{value}</div>
            </div>
          ))}
        </div>

        {excluded && excluded.records > 0 ? (
          <p className="mt-4 rounded-xl border border-wire bg-card-strong/70 px-4 py-3 text-[13px] text-sage">
            <span className="font-semibold text-ink">
              {excluded.records.toLocaleString()}
            </span>{" "}
            {excluded.records === 1 ? "record" : "records"} from{" "}
            <span className="font-semibold text-ink">{excluded.devices}</span>{" "}
            excluded {excluded.devices === 1 ? "device" : "devices"}{" "}
            {excluded.devices === 1 ? "is" : "are"} left out of every count on
            this page, and out of the exports. The rows stay in the database.
          </p>
        ) : null}

        {loading && allDevices == null && (
          <div className="mt-5 h-16 rounded-xl shimmer" />
        )}
      </section>

      {/* Platform sections */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-14 rounded-2xl shimmer" />
          ))}
        </div>
      ) : manifest ? (
        <>
          <PlatformSection platform="android" manifest={manifest} />
          <PlatformSection platform="ios" manifest={manifest} />
        </>
      ) : null}
    </div>
  );
}
