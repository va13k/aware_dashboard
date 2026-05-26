import { useEffect, useState } from "react";
import { exportAllHref, fetchDevices, fetchOverview } from "../api/client";
import {
  ANDROID_SENSOR_CONFIGS,
  IOS_SENSOR_CONFIGS,
  SHARED_SENSOR_CONFIGS,
} from "../config/sensors";
import SensorStatCard from "../components/SensorStatCard";
import ExportLink from "../components/ExportLink";
import type { Device, DevicesResponse, OverviewResponse } from "../types";

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


export default function OverviewPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
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
        const [loadedDevices, loadedOverview] = await Promise.all([
          fetchDevices(),
          fetchOverview(),
        ]);
        if (cancelled) return;
        setDevices(loadedDevices);
        setOverview(loadedOverview);
        setOverviewLoading(false);
        setError(null);
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
  const hasSensorRecords = (key: string) =>
    !!(overview?.android[key] || overview?.ios[key]);
  const shouldShowSensor = (key: string) =>
    !hideEmptySensors || overviewLoading || hasSensorRecords(key);
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
            <ExportLink
              href={exportAllHref()}
              label="Export all"
              title="Export all CSVs"
              className="h-9 px-3 self-start sm:self-center"
            />
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
            {section.sensors.map((config) => (
              <SensorStatCard
                key={config.key}
                config={config}
                androidStats={overview?.android[config.key] ?? null}
                iosStats={overview?.ios[config.key] ?? null}
                loading={overviewLoading}
                className="h-full overflow-hidden"
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
