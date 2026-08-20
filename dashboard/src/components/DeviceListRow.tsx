import type { Device } from "../types";
import { deviceLabel } from "../utils/devices";
import { absoluteTime, relativeAge } from "../utils/time";
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
        <span className="min-w-0 flex-1 truncate text-[14px] font-semibold leading-tight text-ink">
          {deviceLabel(device)}
        </span>
      </div>

      <div className="mt-0.5 truncate text-[12px] text-sage" title={device.device_id}>
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
        {/* Data arrived from a phone the study has no record of joining. Worth a
            badge rather than a page of its own: whoever is looking at the list is
            the person who can say who it is. */}
        {device.excluded ? (
          <span
            title="Left out of the analysis by a researcher. The data is kept and still shown here."
            className="rounded border border-short/40 bg-short/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.3px] text-short"
          >
            excluded
          </span>
        ) : null}
        {device.recognised === false ? (
          <span
            title="This phone is sending data, and the study has no record of it joining. Open it to see what it wrote and how much."
            className="inline-flex items-center rounded-md border border-short/40 bg-short/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.3px] text-short"
          >
            No enrolment record
          </span>
        ) : null}
      </div>

      {/* Three different facts. A phone can be uploading sensor data without
          reporting a study event, and the reverse — and how long it has been
          sending is what separates a phone that appeared this week from one
          reporting since the study opened. */}
      <div className="mt-2 grid grid-cols-3 gap-x-2 text-[12px]">
        <div className="min-w-0">
          <div className="truncate text-sage">First</div>
          <div
            className="truncate font-semibold text-ink"
            title={device.first_seen ? absoluteTime(device.first_seen) : undefined}
          >
            {relativeAge(device.first_seen)}
          </div>
        </div>
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
