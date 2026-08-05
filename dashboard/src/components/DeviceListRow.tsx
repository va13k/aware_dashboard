import type { Device } from "../types";
import { deviceLabel } from "../utils/devices";
import { relativeAge } from "../utils/time";
import { ConfigBadge, EnrollmentBadge } from "./StudyBadges";
import PlatformIcon from "./PlatformIcon";

/**
 * One phone in the list.
 *
 * Every row is the same four stacked regions in the same order, all aligned to
 * the left edge: identity, device id, badges, activity. Nothing is pushed to the
 * right, and nothing moves position depending on how long a phone's name is -
 * long values truncate inside their own region instead.
 */
export default function DeviceListRow({
  device,
  selected,
  onSelect,
}: {
  device: Device;
  selected: boolean;
  onSelect: () => void;
}) {
  const study = device.platform === "android" ? device.study : null;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected}
      className={`w-full min-w-0 cursor-pointer rounded-2xl border px-3.5 py-3 text-left transition-colors ${
        selected
          ? "border-teal bg-teal-soft"
          : "border-wire bg-card-strong hover:bg-teal-soft/50"
      }`}
    >
      <div className="flex min-w-0 items-center gap-2">
        <PlatformIcon platform={device.platform} className="h-4 w-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold leading-tight text-ink">
          {deviceLabel(device)}
        </span>
      </div>

      <div className="mt-0.5 truncate text-[11px] text-sage" title={device.device_id}>
        {device.device_id}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <EnrollmentBadge status={study?.enrollment_status} />
        {study ? (
          <ConfigBadge
            status={study.config_status}
            diffCount={study.diff_count}
          />
        ) : null}
      </div>

      {/* Two different facts. A phone can be uploading sensor data without
          reporting a study event, and the reverse. */}
      <div className="mt-2 grid grid-cols-2 gap-x-2 text-[11px]">
        <div className="min-w-0">
          <div className="truncate text-sage">Upload</div>
          <div className="truncate font-semibold text-ink">
            {relativeAge(device.last_seen)}
          </div>
        </div>
        <div className="min-w-0">
          <div className="truncate text-sage">Study</div>
          <div className="truncate font-semibold text-ink">
            {study ? relativeAge(study.last_study_event_at) : "—"}
          </div>
        </div>
      </div>
    </button>
  );
}
