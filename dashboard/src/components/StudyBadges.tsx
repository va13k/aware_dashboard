import type { StudyConfigStatus, StudyEnrollmentStatus } from "../types";

type Tone = "teal" | "amber" | "red" | "grey";

const TONES: Record<Tone, string> = {
  teal: "bg-teal-soft text-teal border-teal/30",
  amber: "bg-amber-50 text-amber-700 border-amber-300/60",
  red: "bg-red-50 text-red-700 border-red-200",
  grey: "bg-card-strong text-sage border-wire",
};

export function Badge({
  tone,
  children,
  title,
}: {
  tone: Tone;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center rounded-lg border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.4px] ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

const ENROLLMENT: Record<
  StudyEnrollmentStatus,
  { label: string; tone: Tone; title: string }
> = {
  in_study: {
    label: "Enrolled",
    tone: "teal",
    title: "The phone's latest study event says it is in the study",
  },
  left_study: {
    label: "Quit the study",
    tone: "red",
    title: "The phone reported leaving the study",
  },
  unknown: {
    label: "Unknown",
    tone: "grey",
    title: "No study event says whether the phone is in the study",
  },
};

/** Enrollment for an Android phone, or "not tracked" for anything else. */
export function EnrollmentBadge({
  status,
}: {
  status: StudyEnrollmentStatus | null | undefined;
}) {
  if (!status) {
    return (
      <Badge tone="grey" title="iPhones do not report study events">
        Not tracked
      </Badge>
    );
  }

  const { label, tone, title } = ENROLLMENT[status];
  return (
    <Badge tone={tone} title={title}>
      {label}
    </Badge>
  );
}

/**
 * How the phone's installed config compares with the deployed one.
 *
 * A stale config reports how many fields differ, because "stale" alone does not
 * say whether one sampling rate moved or the whole study changed.
 */
export function ConfigBadge({
  status,
  diffCount = 0,
}: {
  status: StudyConfigStatus | null | undefined;
  diffCount?: number;
}) {
  if (status === "current") {
    return (
      <Badge tone="teal" title="Matches the deployed study configuration">
        Current config
      </Badge>
    );
  }

  if (status === "stale") {
    return (
      <Badge
        tone="amber"
        title={`Differs from the deployed configuration in ${diffCount} field${
          diffCount === 1 ? "" : "s"
        }`}
      >
        {diffCount > 0 ? `Stale · ${diffCount}` : "Stale config"}
      </Badge>
    );
  }

  return (
    <Badge tone="grey" title="The phone has not reported a configuration">
      Config unknown
    </Badge>
  );
}
