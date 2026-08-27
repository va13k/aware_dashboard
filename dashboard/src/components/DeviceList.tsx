import { useMemo, useState } from "react";
import type { Device, DevicesResponse, StudyEnrollmentStatus } from "../types";
import { deviceLabel } from "../utils/devices";
import { normalizeTimestamp } from "../utils/time";
import DeviceListRow from "./DeviceListRow";

type StatusFilter = "all" | StudyEnrollmentStatus | "not_tracked";
type PlatformFilter = "all" | "android" | "ios";
type SortOrder = "contact" | "data" | "status" | "name";

const PLATFORM_OPTIONS: { value: PlatformFilter; label: string }[] = [
  { value: "all", label: "All platforms" },
  { value: "android", label: "Android" },
  { value: "ios", label: "iPhone" },
];

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "in_study", label: "Enrolled" },
  { value: "left_study", label: "Quit the study" },
  { value: "unknown", label: "Unknown" },
  { value: "not_tracked", label: "Not tracked" },
];

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: "contact", label: "Recent contact" },
  { value: "data", label: "Recent data" },
  { value: "status", label: "Needs attention" },
  { value: "name", label: "Name" },
];

/** Sorted so the states a researcher has to act on come first. */
const ATTENTION_ORDER: Record<StatusFilter, number> = {
  left_study: 0,
  unknown: 1,
  in_study: 2,
  not_tracked: 3,
  all: 4,
};

function statusOf(device: Device): StatusFilter {
  if (device.platform !== "android" || !device.study) return "not_tracked";
  return device.study.enrollment_status;
}

function compare(a: Device, b: Device, order: SortOrder): number {
  if (order === "name") {
    return deviceLabel(a).localeCompare(deviceLabel(b));
  }

  if (order === "status") {
    const difference = ATTENTION_ORDER[statusOf(a)] - ATTENTION_ORDER[statusOf(b)];
    if (difference !== 0) return difference;
  }

  // Contact is the default operational view; data remains separately sortable
  // because a reachable phone can legitimately have no new sensor measurement.
  const timestamp = (device: Device) =>
    order === "data" ? device.last_sensor_data : device.last_contact;
  const uploadedA = normalizeTimestamp(timestamp(a));
  const uploadedB = normalizeTimestamp(timestamp(b));
  if (uploadedA == null && uploadedB == null) return 0;
  if (uploadedA == null) return 1;
  if (uploadedB == null) return -1;
  return uploadedB - uploadedA;
}

export default function DeviceList({
  devices,
  selected,
  onSelect,
}: {
  devices: DevicesResponse | null;
  selected: Device | null;
  onSelect: (device: Device) => void;
}) {
  const [platform, setPlatform] = useState<PlatformFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [order, setOrder] = useState<SortOrder>("contact");

  const all = useMemo(
    () => (devices ? [...devices.android, ...devices.ios] : []),
    [devices],
  );

  const visible = useMemo(() => {
    const filtered = all.filter(
      (device) =>
        (platform === "all" || device.platform === platform) &&
        (status === "all" || statusOf(device) === status),
    );
    return [...filtered].sort((a, b) => compare(a, b, order));
  }, [all, platform, status, order]);

  const selectClass =
    "min-w-[120px] flex-1 cursor-pointer rounded-xl border border-wire bg-card-strong px-2 py-1.5 text-[12px] font-semibold text-ink";

  return (
    <section className="rounded-3xl border border-wire bg-card p-4 shadow-card backdrop-blur-xl">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h1 className="text-[17px] font-bold text-ink">All devices</h1>
        <p className="shrink-0 text-[12px] text-sage">
          {devices?.android.length ?? 0} Android · {devices?.ios.length ?? 0} iOS
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <select
          aria-label="Filter by platform"
          className={selectClass}
          value={platform}
          onChange={(event) =>
            setPlatform(event.target.value as PlatformFilter)
          }
        >
          {PLATFORM_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by study status"
          className={selectClass}
          value={status}
          onChange={(event) => setStatus(event.target.value as StatusFilter)}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Sort devices"
          className={selectClass}
          value={order}
          onChange={(event) => setOrder(event.target.value as SortOrder)}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {!devices ? (
          <div className="h-24 rounded-xl shimmer sm:col-span-2" />
        ) : visible.length === 0 ? (
          <div className="py-8 text-center text-[14px] text-sage sm:col-span-2">
            {all.length === 0
              ? "No devices"
              : `No devices match these filters (${all.length} hidden)`}
          </div>
        ) : (
          visible.map((device) => (
            <DeviceListRow
              key={`${device.platform}:${device.device_id}`}
              device={device}
              selected={
                device.device_id === selected?.device_id &&
                device.platform === selected?.platform
              }
              onSelect={() => onSelect(device)}
            />
          ))
        )}
      </div>
    </section>
  );
}
