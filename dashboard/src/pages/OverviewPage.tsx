import { useEffect, useState } from "react";
import { exportAllHref, fetchDevices, fetchSensor } from "../api/client";
import { SENSOR_CONFIGS } from "../config/sensors";
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

export default function OverviewPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [sensorData, setSensorData] = useState<SensorData>({});
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(
    new Set(SENSOR_CONFIGS.map((s) => s.key)),
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
          const [androidResults, iosResults] = await Promise.all([
            Promise.all(
              loadedDevices.android.map((d) =>
                fetchSensor("android", d.device_id, sensor.key).catch(
                  () => [] as SensorRecord[],
                ),
              ),
            ),
            Promise.all(
              loadedDevices.ios.map((d) =>
                fetchSensor("ios", d.device_id, sensor.key).catch(
                  () => [] as SensorRecord[],
                ),
              ),
            ),
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

      <div className="grid auto-rows-[220px] grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4 mt-4">
        {SENSOR_CONFIGS.map((config) => (
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
            />
          )
        ))}
      </div>
    </div>
  );
}
