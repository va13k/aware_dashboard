import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLiveRefresh } from "../api/live";
import {
  exportAllHref,
  exportSensorZipHref,
  fetchCountsStatus,
  fetchDevices,
  fetchManifest,
  fetchOrphanCounts,
  fetchStudyDataflow,
  fetchStudyRequirements,
} from "../api/client";
import {
  ANDROID_SENSOR_CONFIGS,
  IOS_SENSOR_CONFIGS,
  SHARED_SENSOR_CONFIGS,
  type SensorConfig,
} from "../config/sensors";
import SensorStatCard from "../components/SensorStatCard";
import CoveragePanel from "../components/CoveragePanel";
import ExportDialog from "../components/ExportDialog";
import SensorViewFilter from "../components/SensorViewFilter";
import { useSensorView } from "../utils/sensorView";
import {
  RequiredEmptyCard,
  RequiredStreamNote,
} from "../components/RequiredByConfig";
import { combinedRequirements } from "../utils/requirements";
import { absoluteTime, normalizeTimestamp, relativeAge } from "../utils/time";
import { deviceLabel } from "../utils/devices";
import type {
  CountsStatus,
  Device,
  DevicesResponse,
  Manifest,
  OrphanCounts,
  SensorManifestEntry,
  StudyDataflow,
  StudyRequirements,
} from "../types";

const CLOCK_INTERVAL_MS = 10000;

interface Section {
  title: string;
  sensors: SensorConfig[];
}

/** Plain words for a dataflow, since "webservice" is our name and not a reader's. */
function dataflowLabel(dataflow: string | null): string {
  if (dataflow === "webservice") return "through the server";
  if (dataflow === "direct") return "straight to the database";
  return "by an unknown route";
}

export default function OverviewPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [view, setView] = useSensorView();
  const [requirements, setRequirements] = useState<StudyRequirements | null>(
    null,
  );
  const [countsStatus, setCountsStatus] = useState<CountsStatus | null>(null);
  const [orphanCounts, setOrphanCounts] = useState<OrphanCounts | null>(null);
  const [studyDataflow, setStudyDataflow] = useState<StudyDataflow | null>(null);
  // The period is chosen in the dialog rather than defaulted, so a
  // study-scale download is never something a single click can start.
  const [exporting, setExporting] = useState(false);
  // Which sensor card asked to export. Its dialog adds the platform question a
  // card needs, since one card spans both.
  const [sensorExport, setSensorExport] = useState<SensorConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Per-sensor totals come from the manifest (absolute, cache-backed) in one
  // request — no per-device row fetching just to count. Devices are still
  // fetched for the "last upload" banner.
  const loadTotals = async () => {
    try {
      const [loadedDevices, loadedManifest] = await Promise.all([
        fetchDevices(),
        fetchManifest(),
      ]);
      setDevices(loadedDevices);
      setManifest(loadedManifest);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };



  // How fresh the numbers on this page are. A refresher that has died leaves a
  // dashboard that looks exactly like a study gone quiet, so the age is shown.
  const loadFreshness = () => {
    fetchCountsStatus()
      .then(setCountsStatus)
      .catch(() => setCountsStatus(null));
    fetchOrphanCounts()
      .then(setOrphanCounts)
      .catch(() => setOrphanCounts(null));
  };

  // Everything on this page counts the whole study, so any arrival is relevant.
  const refresh = () => {
    loadTotals();
    loadFreshness();
  };

  useLiveRefresh(refresh);

  useEffect(() => {
    fetchStudyRequirements()
      .then((data) => setRequirements(data))
      .catch(() => setRequirements(null));
    // Read once: the dataflow changes when a study is reconfigured, not while
    // somebody is looking at the page.
    fetchStudyDataflow()
      .then(setStudyDataflow)
      .catch(() => setStudyDataflow(null));
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNow(Date.now());
    }, CLOCK_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  const allDevices = devices ? [...devices.android, ...devices.ios] : [];
  // A phone that joined the study but has never uploaded has no timestamp to
  // compare, so it can never be the most recent upload.
  const latestUpload = allDevices.reduce<Device | null>((latest, device) => {
    const uploaded = normalizeTimestamp(device.last_seen);
    if (uploaded == null) return latest;
    if (!latest) return device;
    return uploaded > (normalizeTimestamp(latest.last_seen) ?? 0)
      ? device
      : latest;
  }, null);
  const latestUploadText = (() => {
    if (latestUpload) return absoluteTime(latestUpload.last_seen);
    if (devices) return "No uploads yet";
    return "Checking uploads...";
  })();

  // Counts are read from a cache, so the page says how old that cache is. Past
  // the server's threshold it says so plainly rather than showing a stale number
  // as if it were current.
  const countsFreshness = (() => {
    if (!countsStatus) return null;
    const age = countsStatus.age_seconds;
    if (age == null) {
      return { stale: true, text: "Counts have never been refreshed" };
    }
    const minutes = Math.round(age / 60);
    const ago =
      age < 90
        ? "just now"
        : minutes < 60
          ? `${minutes} min ago`
          : `${Math.round(minutes / 60)} h ago`;
    return {
      stale: countsStatus.stale,
      text: countsStatus.stale
        ? `Counts last refreshed ${ago}`
        : `Counts refreshed ${ago}`,
    };
  })();

  const loading = !manifest;
  const entryFor = (
    platform: "android" | "ios",
    key: string,
  ): SensorManifestEntry | null =>
    manifest?.platforms[platform].sensors[key] ?? null;
  const hasSensorRecords = (key: string) =>
    (entryFor("android", key)?.row_count ?? 0) > 0 ||
    (entryFor("ios", key)?.row_count ?? 0) > 0;

  const required = combinedRequirements(requirements);

  // Which sensors, grouped into headed sections, the current view shows.
  const sections: Section[] = (() => {
    const base = [
      { title: "Shared", sensors: SHARED_SENSOR_CONFIGS },
      { title: "Android only", sensors: ANDROID_SENSOR_CONFIGS },
      { title: "iPhone only", sensors: IOS_SENSOR_CONFIGS },
    ];

    if (view === "required") {
      // Every required sensor, even with no data - that gap is the research
      // question - and everything still recording but not required kept under
      // its own heading rather than hidden.
      const requiredSections = base
        .map((section) => ({
          ...section,
          sensors: section.sensors.filter((s) => required.required.has(s.key)),
        }))
        .filter((section) => section.sensors.length > 0);
      // Unrequested data is grouped by platform too: which phones are sending
      // it is the first thing to establish about a sensor nobody asked for.
      const unrequested = base
        .map((section) => ({
          title: `${section.title} - not in config`,
          sensors: section.sensors.filter(
            (s) => !required.required.has(s.key) && hasSensorRecords(s.key),
          ),
        }))
        .filter((section) => section.sensors.length > 0);
      return [...requiredSections, ...unrequested];
    }

    const shouldShow = (key: string) =>
      view === "all" || loading || hasSensorRecords(key);
    return base
      .map((section) => ({
        ...section,
        sensors: section.sensors.filter((s) => shouldShow(s.key)),
      }))
      .filter((section) => view === "all" || section.sensors.length > 0);
  })();

  const visibleSensorCount = sections.reduce(
    (sum, section) => sum + section.sensors.length,
    0,
  );

  const renderCard = (config: SensorConfig) => (
    <SensorStatCard
      config={config}
      android={entryFor("android", config.key)}
      ios={entryFor("ios", config.key)}
      loading={loading}
      className="h-full overflow-hidden"
      onExport={() => setSensorExport(config)}
    />
  );

  if (error)
    return (
      <div className="mt-4 p-4 text-red-700 bg-red-50 border border-red-200 rounded-2xl">
        {error}
      </div>
    );

  return (
    <div>
      <section className="mb-5 rounded-2xl border border-wire bg-card p-4 shadow-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[12px] uppercase tracking-[0.5px] text-sage">
              Last phone data upload
            </p>
            <p className="mt-1 text-[21px] font-bold text-ink">
              {latestUploadText}
            </p>
            {countsFreshness && (
              <p
                className={`mt-1 text-[12px] ${
                  countsFreshness.stale ? "font-semibold text-amber-600" : "text-sage"
                }`}
                title="Record counts are cached and refreshed on a schedule"
              >
                {countsFreshness.text}
              </p>
            )}
          </div>
          {latestUpload && (
            <div className="flex items-center gap-2">
              <Link
                to="/manifest"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Manifest
              </Link>
              <Link
                to="/logs"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Logs
              </Link>
              <button
                type="button"
                onClick={() => setExporting(true)}
                title="Choose a period, then export everything the study holds"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Export all
              </button>
              <div className="rounded-xl bg-teal-soft px-3 py-2 text-right">
                <p className="text-[13px] font-semibold text-teal">
                  {relativeAge(latestUpload.last_seen, now)}
                </p>
                <p className="mt-0.5 text-[12px] text-sage">
                  {latestUpload.platform} - {deviceLabel(latestUpload)}
                </p>
              </div>
            </div>
          )}
          {!latestUpload && devices && (
            <div className="flex items-center gap-2 self-start sm:self-center">
              <Link
                to="/manifest"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Manifest
              </Link>
              <Link
                to="/logs"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Logs
              </Link>
              <button
                type="button"
                onClick={() => setExporting(true)}
                title="Choose a period, then export everything the study holds"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Export all
              </button>
            </div>
          )}
        </div>
      </section>

      {orphanCounts && orphanCounts.records > 0 ? (
        <details className="mb-5 rounded-2xl border border-short/40 bg-short/10 px-4 py-3 text-[13px] text-ink shadow-card">
          <summary className="cursor-pointer font-semibold text-short">
            {orphanCounts.records.toLocaleString()} records have no device id
          </summary>
          <div className="mt-3 space-y-2 text-sage">
            {Object.entries(orphanCounts.platforms).map(([platform, entry]) =>
              entry.records > 0 ? (
                <div key={platform}>
                  <span className="font-semibold capitalize text-ink">
                    {platform}: {entry.records.toLocaleString()}
                  </span>
                  <ul className="mt-1 list-disc pl-5">
                    {Object.entries(entry.tables).map(([table, records]) => (
                      <li key={table}>
                        {table}: {records.toLocaleString()}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null,
            )}
            {/* A count on its own leaves the reader with nothing to do, so this
                says what the rows are, what to check, and who can act. The
                dashboard reads study data and cannot delete it — removing rows
                needs a database administrator. */}
            <p>
              A row lands here when a phone uploaded it before its device id
              resolved. They are left out of every total and every export, so
              nothing on this page is counting them.
            </p>
            <p>
              They are usually attributable: look at which device was writing the
              same table around their timestamps, and they almost certainly belong
              to it. Coverage → pick the sensor → open the hour.
            </p>
            <p>
              Removing or reassigning them is a database administrator's job — the
              dashboard has read-only access to study data. Until someone does,
              they sit here and change nothing.
            </p>
          </div>
        </details>
      ) : null}

      {/* Where the study's data comes in. Two platforms, two answers, and on
          Android it is a choice a researcher made -- so it belongs on screen
          rather than only in a config file. */}
      {studyDataflow ? (
        <div className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-2xl border border-wire bg-card px-4 py-3 text-[13px] text-sage shadow-card">
          <span className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sage">
            Data arrives
          </span>
          <span>
            Android:{" "}
            <span className="font-semibold text-ink">
              {dataflowLabel(studyDataflow.android.dataflow)}
            </span>
            {studyDataflow.android.source === "inferred" ? (
              <span
                className="text-sage/80"
                title="Read from the config's webservice setting. It says so outright once the study is regenerated."
              >
                {" "}
                (inferred)
              </span>
            ) : null}
          </span>
          <span>
            iPhone:{" "}
            <span className="font-semibold text-ink">
              {dataflowLabel(studyDataflow.ios.dataflow)}
            </span>
            <span
              className="text-sage/80"
              title="An iPhone has no direct-database client, so this is not a choice a study makes."
            >
              {" "}
              (always)
            </span>
          </span>
        </div>
      ) : null}

      <CoveragePanel />

      <div className="mb-3 mt-5 flex flex-col gap-2 px-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sage">
          Sensors
        </div>
        <SensorViewFilter value={view} onChange={setView} />
      </div>

      {view === "required" && !required.available ? (
        <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[14px] text-sage shadow-card">
          {requirements
            ? "No deployed config was found to derive sensor requirements from."
            : "Loading sensor requirements…"}
        </div>
      ) : visibleSensorCount === 0 && view !== "all" ? (
        <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[14px] text-sage shadow-card">
          {view === "required"
            ? "The deployed config requires no sensors this dashboard can show."
            : "No sensors have records yet."}
        </div>
      ) : null}

      {sections.map((section) => (
        <section key={section.title} className="mt-5">
          <div className="mb-2 px-1 text-[12px] font-semibold uppercase tracking-[0.6px] text-sage">
            {section.title}
          </div>
          <div className="grid auto-rows-[220px] grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
            {section.sensors.map((config) => {
              const flagged =
                view === "required" &&
                required.required.has(config.key) &&
                !loading &&
                !hasSensorRecords(config.key);
              return (
                <div key={config.key} className="h-full">
                  {flagged ? (
                    <RequiredEmptyCard
                      config={config}
                      className="h-full overflow-hidden"
                    />
                  ) : (
                    renderCard(config)
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {view === "required" && required.available ? (
        <RequiredStreamNote settings={required.requiredWithoutStream} />
      ) : null}

      {sensorExport && (
        <ExportDialog
          title={`Export ${sensorExport.label}`}
          subtitle="Every phone that collected this sensor, for the platforms and period you choose."
          href={(period, platform) =>
            exportSensorZipHref(platform, sensorExport.key, period)
          }
          hasAndroid={sensorExport.tables.android != null}
          hasIos={sensorExport.tables.ios != null}
          sensor={sensorExport.key}
          onClose={() => setSensorExport(null)}
        />
      )}

      {exporting && (
        <ExportDialog
          title="Export the study"
          subtitle="Every sensor and every phone, for the platforms and period you choose."
          href={(period, platform) => exportAllHref(period, platform)}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  );
}
