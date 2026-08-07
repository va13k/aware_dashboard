import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  exportAllHref,
  exportSensorZipHref,
  fetchDevices,
  fetchSensor,
  fetchStudyRequirements,
} from "../api/client";
import {
  ANDROID_SENSOR_CONFIGS,
  IOS_SENSOR_CONFIGS,
  SENSOR_CONFIGS,
  SHARED_SENSOR_CONFIGS,
  type SensorConfig,
} from "../config/sensors";
import SensorStatCard from "../components/SensorStatCard";
import WifiRecordsCard from "../components/WifiRecordsCard";
import ExportLink from "../components/ExportLink";
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
  Device,
  DevicesResponse,
  SensorRecord,
  StudyRequirements,
} from "../types";

type SensorData = Record<
  string,
  { android: SensorRecord[]; ios: SensorRecord[] }
>;

const REFRESH_INTERVAL_MS = 60000;
const CLOCK_INTERVAL_MS = 10000;

function recordsForSensor(
  sensorData: SensorData,
  key: string,
): { android: SensorRecord[]; ios: SensorRecord[] } {
  return sensorData[key] ?? { android: [], ios: [] };
}

interface Section {
  title: string;
  sensors: SensorConfig[];
}

export default function OverviewPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [sensorData, setSensorData] = useState<SensorData>({});
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(
    new Set(SENSOR_CONFIGS.map((s) => s.key)),
  );
  const [view, setView] = useSensorView();
  const [requirements, setRequirements] = useState<StudyRequirements | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    let loading = false;

    async function load() {
      if (loading) return;

      loading = true;
      try {
        const loadedDevices = await fetchDevices();

        if (cancelled) return;

        setDevices(loadedDevices);
        setError(null);

        for (const sensor of SENSOR_CONFIGS) {
          const fetchAndroid =
            sensor.platform === "shared" || sensor.platform === "android";
          const fetchIos =
            sensor.platform === "shared" || sensor.platform === "ios";
          const [androidResults, iosResults] = await Promise.all([
            fetchAndroid
              ? Promise.all(
                  loadedDevices.android.map((d) =>
                    fetchSensor("android", d.device_id, sensor.key).catch(
                      () => [] as SensorRecord[],
                    ),
                  ),
                )
              : Promise.resolve([] as SensorRecord[][]),
            fetchIos
              ? Promise.all(
                  loadedDevices.ios.map((d) =>
                    fetchSensor("ios", d.device_id, sensor.key).catch(
                      () => [] as SensorRecord[],
                    ),
                  ),
                )
              : Promise.resolve([] as SensorRecord[][]),
          ]);

          if (cancelled) return;

          setSensorData((prev) => ({
            ...prev,
            [sensor.key]: {
              android: androidResults.flat(),
              ios: iosResults.flat(),
            },
          }));
          setLoadingKeys((prev) => {
            const next = new Set(prev);
            next.delete(sensor.key);
            return next;
          });
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        loading = false;
      }
    }

    load();
    const intervalId = window.setInterval(load, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    fetchStudyRequirements()
      .then((data) => setRequirements(data))
      .catch(() => setRequirements(null));
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

  const hasSensorRecords = (key: string) => {
    const records = recordsForSensor(sensorData, key);
    return records.android.length + records.ios.length > 0;
  };

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
      const notInConfig = SENSOR_CONFIGS.filter(
        (s) => !required.required.has(s.key) && hasSensorRecords(s.key),
      );
      return notInConfig.length > 0
        ? [...requiredSections, { title: "Not in config", sensors: notInConfig }]
        : requiredSections;
    }

    const shouldShow = (key: string) =>
      view === "all" || loadingKeys.has(key) || hasSensorRecords(key);
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

  const renderCard = (config: SensorConfig) =>
    config.key === "wifi" ? (
      <WifiRecordsCard
        groups={[
          {
            label: "Android",
            records: sensorData[config.key]?.android ?? [],
          },
          {
            label: "iOS",
            records: sensorData[config.key]?.ios ?? [],
          },
        ]}
        loading={loadingKeys.has(config.key)}
        className="h-full overflow-hidden"
        tableClassName="max-h-[138px]"
      />
    ) : (
      <SensorStatCard
        config={config}
        androidRecords={sensorData[config.key]?.android ?? []}
        iosRecords={sensorData[config.key]?.ios ?? []}
        loading={loadingKeys.has(config.key)}
        className="h-full overflow-hidden"
        androidExportHref={
          config.platform === "shared" || config.platform === "android"
            ? exportSensorZipHref("android", config.key)
            : undefined
        }
        iosExportHref={
          config.platform === "shared" || config.platform === "ios"
            ? exportSensorZipHref("ios", config.key)
            : undefined
        }
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
            <p className="text-[11px] uppercase tracking-[0.5px] text-sage">
              Last phone data upload
            </p>
            <p className="mt-1 text-[20px] font-bold text-ink">
              {latestUploadText}
            </p>
          </div>
          {latestUpload && (
            <div className="flex items-center gap-2">
              <Link
                to="/manifest"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[10px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Manifest
              </Link>
              <Link
                to="/logs"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[10px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Logs
              </Link>
              <ExportLink
                href={exportAllHref()}
                label="Export all"
                title="Export all CSVs"
                className="h-9 px-3"
              />
              <div className="rounded-xl bg-teal-soft px-3 py-2 text-right">
                <p className="text-[12px] font-semibold text-teal">
                  {relativeAge(latestUpload.last_seen, now)}
                </p>
                <p className="mt-0.5 text-[11px] text-sage">
                  {latestUpload.platform} - {deviceLabel(latestUpload)}
                </p>
              </div>
            </div>
          )}
          {!latestUpload && devices && (
            <div className="flex items-center gap-2 self-start sm:self-center">
              <Link
                to="/manifest"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[10px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Manifest
              </Link>
              <Link
                to="/logs"
                className="inline-flex h-9 items-center justify-center rounded-lg border border-wire bg-card-strong px-3 text-[10px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                Logs
              </Link>
              <ExportLink
                href={exportAllHref()}
                label="Export all"
                title="Export all CSVs"
                className="h-9 px-3"
              />
            </div>
          )}
        </div>
      </section>

      <div className="mb-3 flex flex-col gap-2 px-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-[0.6px] text-sage">
          Sensors
        </div>
        <SensorViewFilter value={view} onChange={setView} />
      </div>

      {view === "required" && !required.available ? (
        <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[13px] text-sage shadow-card">
          {requirements
            ? "No deployed config was found to derive sensor requirements from."
            : "Loading sensor requirements…"}
        </div>
      ) : visibleSensorCount === 0 && view !== "all" ? (
        <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[13px] text-sage shadow-card">
          {view === "required"
            ? "The deployed config requires no sensors this dashboard can show."
            : "No sensors have records yet."}
        </div>
      ) : null}

      {sections.map((section) => (
        <section key={section.title} className="mt-5">
          <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.6px] text-sage">
            {section.title}
          </div>
          <div className="grid auto-rows-[220px] grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
            {section.sensors.map((config) => {
              const flagged =
                view === "required" &&
                required.required.has(config.key) &&
                !loadingKeys.has(config.key) &&
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
    </div>
  );
}
