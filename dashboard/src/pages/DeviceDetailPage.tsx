import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useHeaderSlot } from "../utils/headerSlot";
import {
  exportDeviceHref,
  fetchDeviceDetail,
  fetchDevices,
  fetchStudyRequirements,
} from "../api/client";
import type { SensorConfig } from "../config/sensors";
import {
  SENSOR_CONFIGS,
  sensorPlatform,
  deviceSensorsForPlatform,
  sensorDataKeys,
} from "../config/sensors";
import SensorTile from "../components/SensorTile";
import DeviceCoveragePanel from "../components/DeviceCoveragePanel";
import SensorModal from "../components/SensorModal";
import LogsModal from "../components/LogsModal";
import ExportDialog from "../components/ExportDialog";
import StudyStatusPanel from "../components/StudyStatusPanel";
import ConfigDiffPanel from "../components/ConfigDiffPanel";
import StudyEventsTimeline from "../components/StudyEventsTimeline";
import WithdrawDevice from "../components/WithdrawDevice";
import SensorViewFilter from "../components/SensorViewFilter";
import { useSensorView } from "../utils/sensorView";
import { RequiredStreamNote } from "../components/RequiredByConfig";
import { platformRequirements } from "../utils/requirements";
import { deviceLabel, deviceOsVersion } from "../utils/devices";
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
  StudyRequirements,
} from "../types";

const POLL_INTERVAL_MS = 60_000;

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
      <div className="text-[11px] uppercase tracking-[0.5px] text-sage">
        {label}
      </div>
      <div className="mt-1 text-[13px] font-semibold text-ink wrap-break-word">
        {formatValue(label, value)}
      </div>
    </div>
  );
}

/** A dropdown for jumping straight to another device. */
function DeviceSwitcher({
  devices,
  selectedKey,
  onSwitch,
}: {
  devices: DevicesResponse | null;
  selectedKey: string | null;
  onSwitch: (platform: string, deviceId: string) => void;
}) {
  if (!devices || (devices.android.length === 0 && devices.ios.length === 0)) {
    return null;
  }

  return (
    <label className="flex items-center gap-2 text-[12px] text-sage">
      Device
      <select
        aria-label="Switch device"
        value={selectedKey ?? ""}
        onChange={(event) => {
          const value = event.target.value;
          const separator = value.indexOf(":");
          if (separator < 0) return;
          onSwitch(value.slice(0, separator), value.slice(separator + 1));
        }}
        className="min-w-[200px] cursor-pointer rounded-lg border border-wire bg-card-strong px-2.5 py-1.5 text-[13px] font-semibold text-ink"
      >
        {selectedKey ? null : <option value="">Select a device</option>}
        {devices.android.length > 0 ? (
          <optgroup label="Android">
            {devices.android.map((device) => (
              <option
                key={device.device_id}
                value={`android:${device.device_id}`}
              >
                {deviceLabel(device)}
              </option>
            ))}
          </optgroup>
        ) : null}
        {devices.ios.length > 0 ? (
          <optgroup label="iOS">
            {devices.ios.map((device) => (
              <option key={device.device_id} value={`ios:${device.device_id}`}>
                {deviceLabel(device)}
              </option>
            ))}
          </optgroup>
        ) : null}
      </select>
    </label>
  );
}

function DeviceDetailPanel({
  detail,
  selected,
  loading,
  onExport,
  deviceName,
}: {
  detail: DeviceDetail | null;
  selected?: Device | null;
  loading: boolean;
  /** Opens the export dialog for this device. */
  onExport?: () => void;
  deviceName?: string;
}) {
  const activeStreams = detail?.streams.filter((s) => s.count > 0) ?? [];
  const osVersion = selected ? deviceOsVersion(selected) : null;

  return (
    <section className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="text-[12px] uppercase tracking-[0.5px] text-sage">
            Device info
          </div>
          <h2 className="text-[16px] font-bold text-ink">
            {deviceName || "Unknown device"}
          </h2>
        </div>
        {detail && (
          <div className="flex items-center gap-2">
            {onExport && (
              <button
                type="button"
                onClick={onExport}
                title="Choose a period, then export this phone's CSVs"
                className="inline-flex h-7 items-center justify-center rounded-lg border border-wire bg-card-strong px-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage transition-colors hover:border-teal hover:text-teal"
              >
                ↓ Export
              </button>
            )}
            <span className="text-[12px] uppercase tracking-[0.5px] text-teal bg-teal-soft px-2 py-1 rounded-lg">
              {detail.platform}
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-32 rounded-xl shimmer" />
      ) : !detail ? (
        <div className="h-32 flex items-center justify-center text-sage text-[14px]">
          Loading device…
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
            {/* What the phone says about itself. A device that has not reported
                its description yet leaves these out rather than showing gaps. */}
            {selected?.manufacturer ? (
              <DetailField label="make" value={selected.manufacturer} />
            ) : null}
            {selected?.hardware ? (
              <DetailField label="hardware" value={selected.hardware} />
            ) : null}
            {osVersion ? <DetailField label="os" value={osVersion} /> : null}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * The most recent record the device uploaded, shown as labelled fields with the
 * sensor it came from. Lives beside the study status rather than cluttering the
 * device summary; rendered for both platforms (the study panel is Android-only).
 */
function LatestPayloadPanel({ detail }: { detail: DeviceDetail }) {
  const withData = detail.streams.filter((s) => s.count > 0 && s.latest);
  if (withData.length === 0) return null;
  const source = withData.reduce((a, b) =>
    (b.last_seen ?? 0) > (a.last_seen ?? 0) ? b : a,
  );
  const entries = source.latest
    ? Object.entries(source.latest).filter(
        ([key]) => !["id", "device_id"].includes(key),
      )
    : [];
  if (entries.length === 0) return null;

  return (
    <section className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-[16px] font-bold text-ink">Latest payload</h2>
        <span className="rounded-md bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 text-[12px] font-semibold text-sage">
          from {source.key}
        </span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
        {entries.map(([key, value]) => (
          <DetailField key={key} label={key} value={value} />
        ))}
      </div>
    </section>
  );
}

export default function DeviceDetailPage() {
  const { platform, deviceId } = useParams<{
    platform?: "android" | "ios";
    deviceId?: string;
  }>();
  const navigate = useNavigate();
  const { setCenter } = useHeaderSlot();
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [view, setView] = useSensorView();
  const [requirements, setRequirements] = useState<StudyRequirements | null>(
    null,
  );
  // The sensor whose time-range chart modal is open, or null when closed.
  const [openConfig, setOpenConfig] = useState<SensorConfig | null>(null);
  // The device's client-logs section is collapsed until opened, so it only
  // fetches when a researcher asks for it.
  const [showLogs, setShowLogs] = useState(false);
  // Which phone asked to export. Its dialog needs no platform question — a
  // device belongs to one — but the count must be narrowed to it.
  const [exportingDevice, setExportingDevice] = useState<Device | null>(null);
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
  const currentDetail =
    detail &&
    selected &&
    detail.platform === selected.platform &&
    detail.device_id === selected.device_id
      ? detail
      : null;
  const platformSensors = selected
    ? deviceSensorsForPlatform(selected.platform)
    : SENSOR_CONFIGS;
  // Counts and last-seen come from the detail endpoint's stream summaries; the
  // grid needs nothing fetched per sensor on load.
  const detailLoading = Boolean(selected && !currentDetail);

  async function refreshParticipation() {
    if (!selected) return;
    const [updatedDetail, updatedDevices] = await Promise.all([
      fetchDeviceDetail(selected.platform, selected.device_id),
      fetchDevices(),
    ]);
    setDetail(updatedDetail);
    setDevices(updatedDevices);
  }

  // Tick every 10 s to keep the "updated X ago" label current.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 10_000);
    return () => clearInterval(id);
  }, []);

  // Only the detail endpoint is fetched (and polled); it carries every sensor's
  // count and last-seen. Per-sensor rows load on demand when a modal opens.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;

    const load = () => {
      fetchDeviceDetail(selected.platform, selected.device_id)
        .then((data) => {
          if (cancelled) return;
          setDetail(data);
          setLastUpdated(Date.now());
        })
        .catch(() => {});
    };

    load();
    const pollId = setInterval(load, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(pollId);
    };
  }, [selected, selectedKey]);

  // Publish the device switcher into the centre of the global header while this
  // page is mounted, and clear it on the way out.
  useEffect(() => {
    const hasDevices =
      devices && (devices.android.length > 0 || devices.ios.length > 0);
    setCenter(
      hasDevices ? (
        <DeviceSwitcher
          devices={devices}
          selectedKey={selectedKey}
          onSwitch={(p, id) =>
            navigate(`/devices/${p}/${encodeURIComponent(id)}`, {
              replace: true,
            })
          }
        />
      ) : null,
    );
    return () => setCenter(null);
  }, [devices, selectedKey, setCenter, navigate]);

  if (error)
    return (
      <div className="mt-4 p-4 text-red-700 bg-red-50 border border-red-200 rounded-2xl">
        {error}
      </div>
    );

  const notFound = Boolean(devices && !selected);

  return (
    <div className="flex flex-col gap-4 min-w-0">
      {/* The switcher lives in the header centre on desktop; on narrow screens
          the header has no room, so it falls back to here. */}
      <div className="flex justify-end md:hidden">
        <DeviceSwitcher
          devices={devices}
          selectedKey={selectedKey}
          onSwitch={(p, id) =>
            navigate(`/devices/${p}/${encodeURIComponent(id)}`, {
              replace: true,
            })
          }
        />
      </div>

      {notFound ? (
        <div className="rounded-2xl border border-wire bg-card p-8 text-center text-[14px] text-sage shadow-card">
          This device is not in the list.{" "}
          <button
            type="button"
            onClick={() => navigate("/devices")}
            className="cursor-pointer font-semibold text-teal underline"
          >
            Back to all devices
          </button>
        </div>
      ) : (
        <>
          <DeviceDetailPanel
            detail={currentDetail}
            selected={selected}
            loading={Boolean(!devices || (selected && !currentDetail))}
            onExport={() => selected && setExportingDevice(selected)}
            deviceName={selected ? deviceLabel(selected) : undefined}
          />

          {currentDetail?.study ? (
            <StudyStatusPanel
              study={currentDetail.study}
              configDiff={currentDetail.config_diff}
            />
          ) : null}

          {selected?.platform === "android" && currentDetail ? (
            <section className="rounded-3xl border border-wire bg-card p-5 shadow-card backdrop-blur-xl">
              <div className="mb-3">
                <p className="text-[12px] uppercase tracking-[0.5px] text-sage">
                  Participation
                </p>
                <h2 className="text-[16px] font-bold text-ink">
                  Enrolment window
                </h2>
              </div>
              <WithdrawDevice
                deviceId={selected.device_id}
                enrolment={currentDetail.enrolment}
                windows={currentDetail.enrolment_windows ?? []}
                onChanged={refreshParticipation}
              />
            </section>
          ) : null}

          {currentDetail ? <LatestPayloadPanel detail={currentDetail} /> : null}

          {currentDetail?.config_diff ? (
            <ConfigDiffPanel diff={currentDetail.config_diff} />
          ) : null}

          {currentDetail?.study ? (
            <StudyEventsTimeline events={currentDetail.study_events ?? []} />
          ) : null}

          {selected ? (
            <DeviceCoveragePanel
              platform={selected.platform}
              deviceId={selected.device_id}
            />
          ) : null}

          {selected &&
            (() => {
              const requiredLookup = platformRequirements(
                requirements,
                selected.platform,
              );
              const requiredSet = requiredLookup.required;

              // Sub-keys that fold into a parent tile rather than get their own:
              // the battery and applications composites each cover several
              // streams behind a single card.
              const FOLDED_KEYS = new Set([
                "battery-charges",
                "battery-discharges",
                "applications-crashes",
                "applications-history",
                "applications-notifications",
              ]);

              // Count and last-seen come straight from the detail endpoint's
              // per-stream summaries (unbounded counts, no page-load fetch).
              const stream = (key: string) =>
                currentDetail?.streams.find((s) => s.key === key);
              const streamCount = (key: string) => stream(key)?.count ?? 0;
              const tileCount = (config: SensorConfig) =>
                sensorDataKeys(config.key).reduce(
                  (sum, key) => sum + streamCount(key),
                  0,
                );
              const tileLastSeen = (config: SensorConfig) =>
                latestTimestamp(
                  sensorDataKeys(config.key).map((key) => stream(key)?.last_seen),
                );
              // While the detail is still loading, show everything; once loaded,
              // "recording" keeps sensors with data and "required" also keeps
              // required-but-empty ones so the gap stays visible.
              const configVisible = (config: SensorConfig) => {
                if (view === "all" || detailLoading) return true;
                const keys = sensorDataKeys(config.key);
                if (keys.some((k) => streamCount(k) > 0)) return true;
                return (
                  view === "required" && keys.some((k) => requiredSet.has(k))
                );
              };
              // Required by the config, loaded, still empty - flagged orange.
              const flagRequired = (config: SensorConfig) =>
                view === "required" &&
                !detailLoading &&
                sensorDataKeys(config.key).some((k) => requiredSet.has(k)) &&
                tileCount(config) === 0;

              const tileConfigs = platformSensors.filter(
                (s) => !FOLDED_KEYS.has(s.key),
              );
              const visibleConfigs = tileConfigs.filter(configVisible);
              const sharedTiles = visibleConfigs.filter(
                (s) => sensorPlatform(s) === "shared",
              );
              const specificTiles = visibleConfigs.filter(
                (s) => sensorPlatform(s) !== "shared",
              );
              const specificLabel =
                selected.platform === "android"
                  ? "Android only"
                  : "iPhone only";

              const renderTile = (config: SensorConfig) => (
                <SensorTile
                  key={config.key}
                  config={config}
                  count={tileCount(config)}
                  lastSeen={tileLastSeen(config)}
                  required={flagRequired(config)}
                  onOpen={() => setOpenConfig(config)}
                />
              );

              return (
                <>
                  <div className="flex flex-col gap-2 px-1 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-1.5 text-[12px] text-sage">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                      {lastUpdated
                        ? `Updated ${relativeAge(lastUpdated)}`
                        : "Loading…"}
                    </div>
                    <SensorViewFilter value={view} onChange={setView} />
                  </div>

                  {view === "required" && !requiredLookup.available ? (
                    <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[14px] text-sage shadow-card">
                      {requirements
                        ? `No deployed ${selected.platform} config was found to derive sensor requirements from.`
                        : "Loading sensor requirements…"}
                    </div>
                  ) : visibleConfigs.length === 0 && view !== "all" ? (
                    <div className="rounded-2xl border border-wire bg-card p-6 text-center text-[14px] text-sage shadow-card">
                      {view === "required"
                        ? "The deployed config requires no sensors this dashboard can show."
                        : "No sensors have records for this device yet."}
                    </div>
                  ) : null}

                  {sharedTiles.length > 0 ? (
                    <>
                      <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sage px-1">
                        Shared
                      </div>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                        {sharedTiles.map(renderTile)}
                      </div>
                    </>
                  ) : null}

                  {specificTiles.length > 0 ? (
                    <>
                      <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sage px-1 mt-2">
                        {specificLabel}
                      </div>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                        {specificTiles.map(renderTile)}
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

          {selected && selected.platform === "android" ? (
            <button
              type="button"
              onClick={() => setShowLogs(true)}
              className="flex w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-wire bg-card p-5 text-left shadow-card transition-colors hover:border-teal hover:bg-teal-soft/40"
            >
              <div>
                <h2 className="text-[16px] font-bold text-ink">Client logs</h2>
                <p className="mt-0.5 text-[12px] text-sage">
                  This device's operation logs — click to open, then filter by
                  type, window or text.
                </p>
              </div>
              <span className="shrink-0 text-sage" aria-hidden>
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M6 4l4 4-4 4"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
            </button>
          ) : null}
        </>
      )}

      {openConfig && selected
        ? (() => {
            const keys = sensorDataKeys(openConfig.key);
            // A trustworthy total comes only from the detail endpoint's
            // unbounded stream counts. If any of the sensor's streams isn't
            // summarised there, the true total is unknown — pass null rather
            // than the page-load fetch length, which is capped and would read
            // as smaller than the in-range count.
            const streamCounts = keys.map(
              (key) => currentDetail?.streams.find((s) => s.key === key)?.count,
            );
            const totalCount = streamCounts.every((c) => c != null)
              ? streamCounts.reduce((sum, c) => sum + (c ?? 0), 0)
              : null;
            // Anchor the preset windows on the sensor's most recent upload,
            // from the detail endpoint's per-stream `last_seen`.
            const anchorTs = latestTimestamp(
              keys.map(
                (key) =>
                  currentDetail?.streams.find((s) => s.key === key)?.last_seen,
              ),
            );
            return (
              <SensorModal
                config={openConfig}
                platform={selected.platform}
                deviceId={selected.device_id}
                totalCount={totalCount}
                anchorTs={anchorTs}
                onClose={() => setOpenConfig(null)}
              />
            );
          })()
        : null}

      {showLogs && selected ? (
        <LogsModal
          deviceId={selected.device_id}
          platform={selected.platform}
          title={deviceLabel(selected)}
          onClose={() => setShowLogs(false)}
        />
      ) : null}

      {exportingDevice ? (
        <ExportDialog
          title={`Export ${deviceLabel(exportingDevice)}`}
          subtitle="Every sensor this phone has data for, over the period you choose."
          href={(period) =>
            exportDeviceHref(
              exportingDevice.platform,
              exportingDevice.device_id,
              period,
            )
          }
          hasAndroid={exportingDevice.platform === "android"}
          hasIos={exportingDevice.platform === "ios"}
          device={exportingDevice.device_id}
          onClose={() => setExportingDevice(null)}
        />
      ) : null}
    </div>
  );
}
