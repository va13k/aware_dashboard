import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchDeviceDetail, fetchDevices, fetchSensor } from "../api/client";
import { SENSOR_CONFIGS } from "../config/sensors";
import SensorTimeSeriesCard from "../components/SensorTimeSeriesCard";
import NetworkTypeCard from "../components/NetworkTypeCard";
import ActivityCard from "../components/ActivityCard";
import type {
  Device,
  DeviceDetail,
  DevicesResponse,
  SensorRecord,
} from "../types";

interface DeviceSensorState {
  key: string | null;
  sensorData: Record<string, SensorRecord[]>;
  networkData: SensorRecord[];
  activityData: SensorRecord[];
  loadingKeys: Set<string>;
  networkLoading: boolean;
  activityLoading: boolean;
}

const EMPTY_SENSOR_STATE: DeviceSensorState = {
  key: null,
  sensorData: {},
  networkData: [],
  activityData: [],
  loadingKeys: new Set(),
  networkLoading: false,
  activityLoading: false,
};

function deviceLabel(d: Device): string {
  if (d.platform === "android") {
    const name = [d.manufacturer, d.model].filter(Boolean).join(" ");
    return name || d.device_id.slice(0, 12);
  }
  return d.device_id.slice(0, 16);
}

function lastSeenLabel(ts: number | null | undefined): string {
  if (!ts) return "never";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatValue(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(3);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DetailField({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0 rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
        {label}
      </div>
      <div className="mt-1 text-[12px] font-semibold text-ink break-words">
        {formatValue(value)}
      </div>
    </div>
  );
}

function DeviceDetailPanel({
  detail,
  loading,
}: {
  detail: DeviceDetail | null;
  loading: boolean;
}) {
  const activeStreams = detail?.streams.filter((s) => s.count > 0) ?? [];
  const latest = activeStreams[0]?.latest ?? detail?.device ?? null;
  const latestEntries = latest
    ? Object.entries(latest)
        .filter(([key]) => !["id", "device_id"].includes(key))
        .slice(0, 8)
    : [];

  return (
    <section className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-[15px] font-bold text-ink">Device info</h2>
          <p className="text-[12px] text-sage mt-0.5">
            {detail
              ? `/api/devices/${detail.platform}/${detail.device_id}`
              : "Select a device"}
          </p>
        </div>
        {detail && (
          <span className="text-[11px] uppercase tracking-[0.5px] text-teal bg-teal-soft px-2 py-1 rounded-lg">
            {detail.platform}
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-32 rounded-xl shimmer" />
      ) : !detail ? (
        <div className="h-32 flex items-center justify-center text-sage text-[13px]">
          Choose a device from the list
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
            <DetailField label="device id" value={detail.device_id} />
            <DetailField
              label="last seen"
              value={lastSeenLabel(
                Math.max(0, ...activeStreams.map((s) => s.last_seen ?? 0)),
              )}
            />
            <DetailField label="streams" value={activeStreams.length} />
            <DetailField
              label="records"
              value={activeStreams.reduce((sum, s) => sum + s.count, 0)}
            />
          </div>

          {latestEntries.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage mb-2">
                Latest payload
              </div>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
                {latestEntries.map(([key, value]) => (
                  <DetailField key={key} label={key} value={value} />
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-sage mb-2">
              Data streams
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
              {detail.streams.map((stream) => (
                <div
                  key={stream.key}
                  className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-semibold text-ink">
                      {stream.key}
                    </span>
                    <span className="text-[11px] text-sage">
                      {stream.count.toLocaleString()}
                    </span>
                  </div>
                  <div className="text-[11px] text-sage mt-1">
                    {lastSeenLabel(stream.last_seen)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default function DevicePage() {
  const { platform, deviceId } = useParams<{
    platform?: "android" | "ios";
    deviceId?: string;
  }>();
  const navigate = useNavigate();
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [sensorState, setSensorState] =
    useState<DeviceSensorState>(EMPTY_SENSOR_STATE);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDevices()
      .then((d) => setDevices(d))
      .catch((e) => setError(String(e)));
  }, []);

  const allDevices: Device[] = useMemo(
    () => (devices ? [...devices.android, ...devices.ios] : []),
    [devices],
  );
  const selected =
    allDevices.find(
      (d) => d.device_id === deviceId && (!platform || d.platform === platform),
    ) ?? null;
  const selectedKey = selected
    ? `${selected.platform}:${selected.device_id}`
    : null;
  const currentDetail =
    detail &&
    selected &&
    detail.platform === selected.platform &&
    detail.device_id === selected.device_id
      ? detail
      : null;
  const currentSensorState =
    sensorState.key === selectedKey ? sensorState : EMPTY_SENSOR_STATE;
  const pendingSensorKeys =
    currentSensorState.key === selectedKey
      ? currentSensorState.loadingKeys
      : new Set(SENSOR_CONFIGS.map((s) => s.key));

  useEffect(() => {
    if (!selected) return;

    let cancelled = false;

    fetchDeviceDetail(selected.platform, selected.device_id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });

    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;

    for (const sensor of SENSOR_CONFIGS) {
      fetchSensor(selected.platform, selected.device_id, sensor.key)
        .then((records) => {
          if (cancelled) return;
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            sensorData: {
              ...(prev.key === selectedKey ? prev.sensorData : {}),
              [sensor.key]: records,
            },
          }));
        })
        .catch(() => {
          if (cancelled) return;
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            sensorData: {
              ...(prev.key === selectedKey ? prev.sensorData : {}),
              [sensor.key]: [],
            },
          }));
        })
        .finally(() => {
          if (cancelled) return;
          setSensorState((prev) => {
            const base =
              prev.key === selectedKey
                ? prev
                : {
                    key: selectedKey,
                    sensorData: {},
                    networkData: [],
                    activityData: [],
                    loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                    networkLoading: true,
                    activityLoading: true,
                  };
            const next = new Set(base.loadingKeys);
            next.delete(sensor.key);
            return { ...base, loadingKeys: next };
          });
        });
    }

    fetchSensor(selected.platform, selected.device_id, "network")
      .then((records) => {
        if (!cancelled) {
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            networkData: records,
            networkLoading: false,
          }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            networkData: [],
            networkLoading: false,
          }));
        }
      });

    fetchSensor(selected.platform, selected.device_id, "activity")
      .then((records) => {
        if (!cancelled) {
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            activityData: records,
            activityLoading: false,
          }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSensorState((prev) => ({
            ...(prev.key === selectedKey
              ? prev
              : {
                  key: selectedKey,
                  sensorData: {},
                  networkData: [],
                  activityData: [],
                  loadingKeys: new Set(SENSOR_CONFIGS.map((s) => s.key)),
                  networkLoading: true,
                  activityLoading: true,
                }),
            activityData: [],
            activityLoading: false,
          }));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selected, selectedKey]);

  if (error)
    return (
      <div className="mt-4 p-4 text-red-700 bg-red-50 border border-red-200 rounded-2xl">
        {error}
      </div>
    );

  return (
    <div className="grid grid-cols-[minmax(280px,360px)_1fr] gap-5 items-start max-xl:grid-cols-1">
      <section className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h1 className="text-[16px] font-bold text-ink">All devices</h1>
            <p className="text-[12px] text-sage mt-0.5">
              {(allDevices.length || 0).toLocaleString()} total
            </p>
          </div>
          <div className="flex gap-1.5 text-[11px] text-sage">
            <span className="px-2 py-1 rounded-lg bg-card-strong border border-wire">
              {devices?.android.length ?? 0} Android
            </span>
            <span className="px-2 py-1 rounded-lg bg-card-strong border border-wire">
              {devices?.ios.length ?? 0} iOS
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2 max-xl:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">
          {!devices ? (
            <div className="h-24 rounded-xl shimmer" />
          ) : allDevices.length === 0 ? (
            <div className="text-sage text-[13px] py-8 text-center">
              No devices
            </div>
          ) : (
            allDevices.map((d) => {
              const isSelected =
                d.device_id === selected?.device_id &&
                d.platform === selected?.platform;
              return (
                <button
                  key={`${d.platform}:${d.device_id}`}
                  onClick={() =>
                    navigate(
                      `/devices/${d.platform}/${encodeURIComponent(d.device_id)}`,
                    )
                  }
                  className={`w-full text-left px-3.5 py-3 rounded-2xl border transition-colors cursor-pointer
                  ${
                    isSelected
                      ? "bg-teal-soft border-teal"
                      : "bg-card-strong border-wire hover:bg-teal-soft/50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span
                      className={`text-[11px] uppercase tracking-[0.5px] font-semibold ${isSelected ? "text-teal" : "text-sage"}`}
                    >
                      {d.platform}
                    </span>
                    <span className="text-[11px] text-sage">
                      {lastSeenLabel(d.last_seen)}
                    </span>
                  </div>
                  <div className="text-[13px] font-semibold leading-tight truncate text-ink">
                    {deviceLabel(d)}
                  </div>
                  <div className="text-[11px] text-sage mt-1 truncate">
                    {d.device_id}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </section>

      <div className="flex flex-col gap-4 min-w-0">
        <DeviceDetailPanel
          detail={currentDetail}
          loading={Boolean(selected && !currentDetail)}
        />

        {selected && (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
            {SENSOR_CONFIGS.map((config) => (
              <SensorTimeSeriesCard
                key={config.key}
                config={config}
                records={currentSensorState.sensorData[config.key] ?? []}
                loading={pendingSensorKeys.has(config.key)}
              />
            ))}
            <NetworkTypeCard
              records={currentSensorState.networkData}
              loading={
                currentSensorState.key !== selectedKey ||
                currentSensorState.networkLoading
              }
            />
            <ActivityCard
              records={currentSensorState.activityData}
              loading={
                currentSensorState.key !== selectedKey ||
                currentSensorState.activityLoading
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
