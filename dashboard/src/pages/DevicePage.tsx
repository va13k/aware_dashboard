import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  exportDeviceHref,
  exportSensorHref,
  fetchDeviceDetail,
  fetchDevices,
  fetchSensor,
  fetchStudyRequirements,
} from "../api/client";
import { SENSOR_CONFIGS, deviceSensorsForPlatform } from "../config/sensors";
import SensorTimeSeriesCard from "../components/SensorTimeSeriesCard";
import NetworkTypeCard from "../components/NetworkTypeCard";
import ActivityCard from "../components/ActivityCard";
import ApplicationsCard from "../components/ApplicationsCard";
import WifiRecordsCard from "../components/WifiRecordsCard";
import LocationRecordsCard from "../components/LocationRecordsCard";
import CallsRecordsCard from "../components/CallsRecordsCard";
import TimezoneRecordsCard from "../components/TimezoneRecordsCard";
import AccelerometerRecordsCard from "../components/AccelerometerRecordsCard";
import BluetoothRecordsCard from "../components/BluetoothRecordsCard";
import GyroscopeRecordsCard from "../components/GyroscopeRecordsCard";
import LinearAccelerometerRecordsCard from "../components/LinearAccelerometerRecordsCard";
import ConversationRecordsCard from "../components/ConversationRecordsCard";
import DeviceUsageRecordsCard from "../components/DeviceUsageRecordsCard";
import ProcessorCard from "../components/ProcessorCard";
import BatteryEventsCard from "../components/BatteryEventsCard";
import AmbientNoiseCard from "../components/AmbientNoiseCard";
import ExportLink from "../components/ExportLink";
import DeviceList from "../components/DeviceList";
import StudyStatusPanel from "../components/StudyStatusPanel";
import ConfigDiffPanel from "../components/ConfigDiffPanel";
import StudyEventsTimeline from "../components/StudyEventsTimeline";
import SensorViewFilter from "../components/SensorViewFilter";
import { useSensorView } from "../utils/sensorView";
import {
  RequiredEmptyCard,
  RequiredStreamNote,
} from "../components/RequiredByConfig";
import { platformRequirements } from "../utils/requirements";
import {
  absoluteTime,
  latestTimestamp,
  normalizeTimestamp,
  relativeAge,
} from "../utils/time";
import type {
  Device,
  DeviceDetail,
  DevicesResponse,
  SensorRecord,
  StudyRequirements,
} from "../types";

const POLL_INTERVAL_MS = 60_000;

interface DeviceSensorState {
  key: string | null;
  sensorData: Record<string, SensorRecord[]>;
  loadingKeys: Set<string>;
}

const EMPTY_SENSOR_STATE: DeviceSensorState = {
  key: null,
  sensorData: {},
  loadingKeys: new Set(),
};

function formatValue(label: string, value: unknown): string {
  if (value == null || value === "") return "-";
  if (label.toLowerCase().includes("timestamp")) {
    if (normalizeTimestamp(value) != null) return absoluteTime(value);
  }
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
      <div className="mt-1 text-[12px] font-semibold text-ink wrap-break-word">
        {formatValue(label, value)}
      </div>
    </div>
  );
}

function DeviceDetailPanel({
  detail,
  loading,
  exportHref,
}: {
  detail: DeviceDetail | null;
  loading: boolean;
  exportHref?: string;
}) {
  const activeStreams = detail?.streams.filter((s) => s.count > 0) ?? [];
  const latest = activeStreams[0]?.latest ?? detail?.device ?? null;
  const latestEntries = latest
    ? Object.entries(latest).filter(
        ([key]) => !["id", "device_id"].includes(key),
      )
    : [];

  return (
    <section className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-[15px] font-bold text-ink">Device info</h2>
        </div>
        {detail && (
          <div className="flex items-center gap-2">
            {exportHref && (
              <ExportLink
                href={exportHref}
                label="ZIP"
                title="Export device CSVs"
              />
            )}
            <span className="text-[11px] uppercase tracking-[0.5px] text-teal bg-teal-soft px-2 py-1 rounded-lg">
              {detail.platform}
            </span>
          </div>
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
              value={relativeAge(
                latestTimestamp(activeStreams.map((s) => s.last_seen)),
              )}
            />
            <DetailField label="sensors" value={activeStreams.length} />
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
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [view, setView] = useSensorView();
  const [requirements, setRequirements] = useState<StudyRequirements | null>(
    null,
  );
  // Ticks every 10 s so the "X ago" label stays fresh without re-fetching.
  const [, setTick] = useState(0);

  useEffect(() => {
    fetchDevices()
      .then((d) => setDevices(d))
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    fetchStudyRequirements()
      .then((data) => setRequirements(data))
      .catch(() => setRequirements(null));
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
  const selectedDeviceExportHref = selected
    ? exportDeviceHref(selected.platform, selected.device_id)
    : undefined;
  const selectedSensorExportHref = (sensor: string) =>
    selected
      ? exportSensorHref(selected.platform, selected.device_id, sensor)
      : undefined;
  const currentDetail =
    detail &&
    selected &&
    detail.platform === selected.platform &&
    detail.device_id === selected.device_id
      ? detail
      : null;
  const currentSensorState =
    sensorState.key === selectedKey ? sensorState : EMPTY_SENSOR_STATE;
  const platformSensors = selected
    ? deviceSensorsForPlatform(selected.platform)
    : SENSOR_CONFIGS;
  const pendingSensorKeys =
    currentSensorState.key === selectedKey
      ? currentSensorState.loadingKeys
      : new Set(platformSensors.map((s) => s.key));

  // Tick every 10 s to keep the "updated X ago" label current.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 10_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const isFirstRun = { value: true };

    const sensors = deviceSensorsForPlatform(selected.platform);
    const initialLoadingKeys = new Set(sensors.map((s) => s.key));

    const makeEmpty = (): DeviceSensorState => ({
      key: selectedKey,
      sensorData: {},
      loadingKeys: initialLoadingKeys,
    });

    const fetchAll = () => {
      const initial = isFirstRun.value;
      isFirstRun.value = false;

      if (initial) {
        setLastUpdated(null);
        setSensorState(makeEmpty());
      }

      fetchDeviceDetail(selected.platform, selected.device_id)
        .then((data) => {
          if (!cancelled) setDetail(data);
        })
        .catch(() => {});

      for (const sensor of sensors) {
        fetchSensor(selected.platform, selected.device_id, sensor.key)
          .then((records) => {
            if (cancelled) return;
            setSensorState((prev) => {
              const base = prev.key === selectedKey ? prev : makeEmpty();
              const updated: DeviceSensorState = {
                ...base,
                sensorData: { ...base.sensorData, [sensor.key]: records },
              };
              if (initial) {
                const keys = new Set(base.loadingKeys);
                keys.delete(sensor.key);
                updated.loadingKeys = keys;
              }
              return updated;
            });
          })
          .catch(() => {
            if (cancelled) return;
            setSensorState((prev) => {
              const base = prev.key === selectedKey ? prev : makeEmpty();
              const updated: DeviceSensorState = {
                ...base,
                sensorData: { ...base.sensorData, [sensor.key]: [] },
              };
              if (initial) {
                const keys = new Set(base.loadingKeys);
                keys.delete(sensor.key);
                updated.loadingKeys = keys;
              }
              return updated;
            });
          });
      }

      if (!cancelled) setLastUpdated(Date.now());
    };

    fetchAll();
    const pollId = setInterval(fetchAll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(pollId);
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
      <DeviceList
        devices={devices}
        selected={selected}
        onSelect={(device) =>
          navigate(
            `/devices/${device.platform}/${encodeURIComponent(device.device_id)}`,
            { replace: true },
          )
        }
      />

      <div className="flex flex-col gap-4 min-w-0">
        <DeviceDetailPanel
          detail={currentDetail}
          loading={Boolean(selected && !currentDetail)}
          exportHref={selectedDeviceExportHref}
        />

        {currentDetail?.study ? (
          <StudyStatusPanel
            study={currentDetail.study}
            configDiff={currentDetail.config_diff}
          />
        ) : null}

        {currentDetail?.config_diff ? (
          <ConfigDiffPanel diff={currentDetail.config_diff} />
        ) : null}

        {currentDetail?.study ? (
          <StudyEventsTimeline events={currentDetail.study_events ?? []} />
        ) : null}

        {selected &&
          (() => {
            const sharedSensors = platformSensors.filter(
              (s) => s.platform === "shared",
            );
            const sensorRecords = (key: string) =>
              currentSensorState.sensorData[key] ?? [];
            const sensorLoading = (key: string) => pendingSensorKeys.has(key);
            const hasRecords = (key: string) => sensorRecords(key).length > 0;
            const requiredLookup = platformRequirements(
              requirements,
              selected.platform,
            );
            const requiredSet = requiredLookup.required;
            // A group - one key, or the several keys behind a composite card - is
            // shown when any key has data or is still loading; in the required
            // view it also shows when the config asks for it, even with nothing
            // recorded yet.
            const groupVisible = (keys: string[]) => {
              if (view === "all") return true;
              if (keys.some((k) => sensorLoading(k) || hasRecords(k)))
                return true;
              return view === "required" && keys.some((k) => requiredSet.has(k));
            };
            const shouldShowSensor = (key: string) => groupVisible([key]);
            // Required by the config, done loading, and still empty - the gap the
            // required view exists to surface.
            const flagRequired = (key: string) =>
              view === "required" &&
              requiredSet.has(key) &&
              !sensorLoading(key) &&
              !hasRecords(key);
            // Fill the grid cell (`h-full` on both the wrapper and the card
            // div it holds) so every card in a row shares the row's height and
            // the rows stop looking ragged. A required-but-empty sensor renders
            // the orange placeholder instead of its own (empty) card.
            const withFlag = (
              key: string,
              node: React.ReactNode,
              className = "",
            ) => {
              const config = platformSensors.find((s) => s.key === key);
              const content =
                flagRequired(key) && config ? (
                  <RequiredEmptyCard config={config} />
                ) : (
                  node
                );
              return (
                <div
                  key={key}
                  className={`h-full [&>div]:h-full ${className}`.trim()}
                >
                  {content}
                </div>
              );
            };
            const visibleSharedSensors = sharedSensors.filter((sensor) =>
              shouldShowSensor(sensor.key),
            );
            const locationSensor = visibleSharedSensors.find(
              (s) => s.key === "locations",
            );
            const BATTERY_KEYS = [
              "battery",
              "battery-charges",
              "battery-discharges",
            ];
            const shouldShowBatteryCard = groupVisible(BATTERY_KEYS);
            const sharedChartSensors = visibleSharedSensors.filter(
              (s) =>
                !["locations", "network", ...BATTERY_KEYS].includes(s.key),
            );
            const showNetwork = shouldShowSensor("network");
            const APP_SUB_KEYS = new Set([
              "applications-crashes",
              "applications-history",
              "applications-notifications",
            ]);
            const ALL_APP_KEYS = [
              "applications",
              "applications-crashes",
              "applications-history",
              "applications-notifications",
            ];
            const shouldShowApplications = groupVisible(ALL_APP_KEYS);
            const specificSensors = platformSensors.filter(
              (s) =>
                s.platform !== "shared" &&
                !APP_SUB_KEYS.has(s.key) &&
                (s.key === "applications"
                  ? shouldShowApplications
                  : shouldShowSensor(s.key)),
            );
            const specificLabel =
              selected.platform === "android" ? "Android only" : "iPhone only";
            const showSharedSection =
              sharedChartSensors.length > 0 ||
              locationSensor != null ||
              showNetwork ||
              shouldShowBatteryCard;
            const visibleSensorCount =
              sharedChartSensors.length +
              (locationSensor ? 1 : 0) +
              (showNetwork ? 1 : 0) +
              (shouldShowBatteryCard ? 1 : 0) +
              specificSensors.length;

            return (
              <>
                <div className="flex flex-col gap-2 px-1 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] text-sage">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                    {lastUpdated
                      ? `Updated ${relativeAge(lastUpdated)}`
                      : "Loading…"}
                  </div>
                  <SensorViewFilter value={view} onChange={setView} />
                </div>

                {view === "required" && !requiredLookup.available ? (
                  <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[13px] text-sage shadow-card">
                    {requirements
                      ? `No deployed ${selected.platform} config was found to derive sensor requirements from.`
                      : "Loading sensor requirements…"}
                  </div>
                ) : visibleSensorCount === 0 && view !== "all" ? (
                  <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[13px] text-sage shadow-card">
                    {view === "required"
                      ? "The deployed config requires no sensors this dashboard can show."
                      : "No sensors have records for this device yet."}
                  </div>
                ) : null}

                {showSharedSection ? (
                  <>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.6px] text-sage px-1">
                      Shared
                    </div>
                    <div className="grid grid-flow-dense grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
                      {sharedChartSensors.map((config) =>
                        withFlag(
                          config.key,
                          config.key === "calls" ? (
                          <CallsRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "accelerometer" ? (
                          <AccelerometerRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "bluetooth" ? (
                          <BluetoothRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "gyroscope" ? (
                          <GyroscopeRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "linear-accelerometer" ? (
                          <LinearAccelerometerRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "timezone" ? (
                          <TimezoneRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "wifi" ? (
                          <WifiRecordsCard
                            key={config.key}
                            groups={[
                              {
                                label: selected.platform,
                                records:
                                  currentSensorState.sensorData[config.key] ??
                                  [],
                              },
                            ]}
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "processor" ? (
                          <ProcessorCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "plugin-ambient-noise" ? (
                          <AmbientNoiseCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : (
                          <SensorTimeSeriesCard
                            key={config.key}
                            config={config}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                          ),
                          config.key === "bluetooth" ? "col-span-2" : "",
                        ),
                      )}
                      {showNetwork
                        ? withFlag(
                            "network",
                            <NetworkTypeCard
                              records={sensorRecords("network")}
                              loading={sensorLoading("network")}
                              platform={selected.platform}
                              exportHref={selectedSensorExportHref("network")}
                            />,
                          )
                        : null}
                      {shouldShowBatteryCard ? (
                        <div className="col-span-full">
                          <BatteryEventsCard
                            batteryRecords={sensorRecords("battery")}
                            batteryLoading={sensorLoading("battery")}
                            batteryExportHref={selectedSensorExportHref(
                              "battery",
                            )}
                            chargesRecords={sensorRecords("battery-charges")}
                            dischargesRecords={sensorRecords(
                              "battery-discharges",
                            )}
                            chargesLoading={sensorLoading("battery-charges")}
                            dischargesLoading={sensorLoading(
                              "battery-discharges",
                            )}
                            chargesExportHref={selectedSensorExportHref(
                              "battery-charges",
                            )}
                            dischargesExportHref={selectedSensorExportHref(
                              "battery-discharges",
                            )}
                          />
                        </div>
                      ) : null}
                    </div>

                    {locationSensor
                      ? withFlag(
                          locationSensor.key,
                          <LocationRecordsCard
                            records={
                              currentSensorState.sensorData[
                                locationSensor.key
                              ] ?? []
                            }
                            loading={pendingSensorKeys.has(locationSensor.key)}
                            exportHref={selectedSensorExportHref(
                              locationSensor.key,
                            )}
                          />,
                        )
                      : null}
                  </>
                ) : null}

                {specificSensors.length > 0 ? (
                  <>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.6px] text-sage px-1 mt-2">
                      {specificLabel}
                    </div>
                    <div className="grid grid-flow-dense grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
                      {specificSensors.map((config) =>
                        withFlag(
                          config.key,
                          config.key === "studentlife-audio" ? (
                          <ConversationRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "fused-location" ? (
                          <LocationRecordsCard
                            key={config.key}
                            title="Fused Location"
                            color="#16a34a"
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "device-usage" ? (
                          <DeviceUsageRecordsCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "activity" ? (
                          <ActivityCard
                            key={config.key}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                        ) : config.key === "applications" ? (
                          <div key={config.key} className="col-span-full">
                            <ApplicationsCard
                              foregroundRecords={sensorRecords("applications")}
                              crashRecords={sensorRecords(
                                "applications-crashes",
                              )}
                              historyRecords={sensorRecords(
                                "applications-history",
                              )}
                              notificationRecords={sensorRecords(
                                "applications-notifications",
                              )}
                              foregroundLoading={sensorLoading("applications")}
                              crashLoading={sensorLoading(
                                "applications-crashes",
                              )}
                              historyLoading={sensorLoading(
                                "applications-history",
                              )}
                              notificationLoading={sensorLoading(
                                "applications-notifications",
                              )}
                              exportHref={selectedSensorExportHref(config.key)}
                            />
                          </div>
                        ) : (
                          <SensorTimeSeriesCard
                            key={config.key}
                            config={config}
                            records={
                              currentSensorState.sensorData[config.key] ?? []
                            }
                            loading={pendingSensorKeys.has(config.key)}
                            exportHref={selectedSensorExportHref(config.key)}
                          />
                          ),
                          config.key === "applications"
                            ? "col-span-full"
                            : "",
                        ),
                      )}
                    </div>
                  </>
                ) : null}

                {view === "required" && requiredLookup.available ? (
                  <RequiredStreamNote
                    settings={requiredLookup.requiredWithoutStream}
                  />
                ) : null}
              </>
            );
          })()}
      </div>
    </div>
  );
}
