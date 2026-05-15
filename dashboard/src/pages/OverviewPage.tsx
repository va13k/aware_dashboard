import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { exportAllHref, exportSensorZipHref, fetchDevices, fetchSensor } from "../api/client";
import {
  ANDROID_SENSOR_CONFIGS,
  IOS_SENSOR_CONFIGS,
  SENSOR_CONFIGS,
  SHARED_SENSOR_CONFIGS,
} from "../config/sensors";
import SensorStatCard from "../components/SensorStatCard";
import WifiRecordsCard from "../components/WifiRecordsCard";
import ExportLink from "../components/ExportLink";
import type { Device, DevicesResponse, SensorRecord } from "../types";

type SensorData = Record<
  string,
  { android: SensorRecord[]; ios: SensorRecord[] }
>;

const REFRESH_INTERVAL_MS = 60000;
const CLOCK_INTERVAL_MS = 10000;
const SENSOR_FILTER_STORAGE_KEY = "aware-dashboard-hide-empty-sensors";

function deviceLabel(device: Device): string {
  if (device.platform === "android") {
    const name = [device.manufacturer, device.model].filter(Boolean).join(" ");
    return name || device.device_id.slice(0, 12);
  }

  return device.device_id.slice(0, 16);
}

function normalizeTimestamp(timestamp: number): number {
  return timestamp < 100000000000 ? timestamp * 1000 : timestamp;
}

function formatUploadDate(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(normalizeTimestamp(timestamp)));
}

function uploadAgeLabel(timestamp: number, now: number): string {
  const diff = (now - normalizeTimestamp(timestamp)) / 1000;

  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function readHideEmptySensors(): boolean {
  return window.localStorage.getItem(SENSOR_FILTER_STORAGE_KEY) === "true";
}

function recordsForSensor(
  sensorData: SensorData,
  key: string,
): { android: SensorRecord[]; ios: SensorRecord[] } {
  return sensorData[key] ?? { android: [], ios: [] };
}

export default function OverviewPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [sensorData, setSensorData] = useState<SensorData>({});
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(
    new Set(SENSOR_CONFIGS.map((s) => s.key)),
  );
  const [hideEmptySensors, setHideEmptySensors] = useState(
    readHideEmptySensors,
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
    const intervalId = window.setInterval(() => {
      setNow(Date.now());
    }, CLOCK_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      SENSOR_FILTER_STORAGE_KEY,
      String(hideEmptySensors),
    );
  }, [hideEmptySensors]);

  const allDevices = devices ? [...devices.android, ...devices.ios] : [];
  const latestUpload = allDevices.reduce<Device | null>((latest, device) => {
    if (!latest) return device;
    return normalizeTimestamp(device.last_seen) >
      normalizeTimestamp(latest.last_seen)
      ? device
      : latest;
  }, null);
  const latestUploadText = (() => {
    if (latestUpload) return formatUploadDate(latestUpload.last_seen);
    if (devices) return "No uploads yet";
    return "Checking uploads...";
  })();
  const hasSensorRecords = (key: string) => {
    const records = recordsForSensor(sensorData, key);
    return records.android.length + records.ios.length > 0;
  };
  const shouldShowSensor = (key: string) =>
    !hideEmptySensors || loadingKeys.has(key) || hasSensorRecords(key);
  const visibleSections = [
    { title: "Shared", sensors: SHARED_SENSOR_CONFIGS },
    { title: "Android only", sensors: ANDROID_SENSOR_CONFIGS },
    { title: "iPhone only", sensors: IOS_SENSOR_CONFIGS },
  ]
    .map((section) => ({
      ...section,
      sensors: section.sensors.filter((sensor) => shouldShowSensor(sensor.key)),
    }))
    .filter((section) => !hideEmptySensors || section.sensors.length > 0);
  const visibleSensorCount = visibleSections.reduce(
    (sum, section) => sum + section.sensors.length,
    0,
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
              <ExportLink
                href={exportAllHref()}
                label="Export all"
                title="Export all CSVs"
                className="h-9 px-3"
              />
              <div className="rounded-xl bg-teal-soft px-3 py-2 text-right">
                <p className="text-[12px] font-semibold text-teal">
                  {uploadAgeLabel(latestUpload.last_seen, now)}
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
        <label className="flex cursor-pointer items-center gap-2 self-start rounded-xl border border-wire bg-card px-3 py-2 text-[12px] font-semibold text-ink shadow-card sm:self-auto">
          <input
            type="checkbox"
            checked={hideEmptySensors}
            onChange={(event) => setHideEmptySensors(event.target.checked)}
            className="h-4 w-4 accent-teal"
          />
          Only sensors with records
        </label>
      </div>

      {visibleSensorCount === 0 && hideEmptySensors ? (
        <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[13px] text-sage shadow-card">
          No sensors have records yet.
        </div>
      ) : null}

      {visibleSections.map((section) => (
        <section key={section.title} className="mt-5">
          <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.6px] text-sage">
            {section.title}
          </div>
          <div className="grid auto-rows-[220px] grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4">
            {section.sensors.map((config) =>
              config.key === "wifi" ? (
                <WifiRecordsCard
                  key={config.key}
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
                  key={config.key}
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
              ),
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
