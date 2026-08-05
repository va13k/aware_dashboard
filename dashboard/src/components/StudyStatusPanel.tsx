import type { AndroidStudySummary, ConfigDiff } from "../types";
import { durationLabel, isoDateTime, relativeAge } from "../utils/time";
import { ConfigBadge, EnrollmentBadge } from "./StudyBadges";

function Field({
  label,
  value,
  title,
}: {
  label: string;
  value: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
        {label}
      </div>
      <div
        className="mt-1 text-[12px] font-semibold text-ink wrap-break-word"
        title={title}
      >
        {value}
      </div>
    </div>
  );
}

/** Approved consents are teal, declined are red, and "none" is stated in words. */
function ConsentChips({
  consents,
  tone,
  emptyLabel,
}: {
  consents: string[];
  tone: "teal" | "red";
  emptyLabel: string;
}) {
  if (consents.length === 0) {
    return <span className="text-[12px] text-sage">{emptyLabel}</span>;
  }

  const toneClass =
    tone === "teal"
      ? "bg-teal-soft text-teal border-teal/30"
      : "bg-red-50 text-red-700 border-red-200";

  return (
    <div className="flex flex-wrap gap-1.5">
      {consents.map((consent) => (
        <span
          key={consent}
          className={`inline-flex items-center rounded-lg border px-2 py-0.5 text-[11px] font-semibold ${toneClass}`}
        >
          {consent}
        </span>
      ))}
    </div>
  );
}

/**
 * Enrollment, consent and rejoin history for one Android phone.
 *
 * iPhones do not report a study log, so this panel is only rendered for Android
 * devices; there is no iOS equivalent to fall back to.
 */
export default function StudyStatusPanel({
  study,
  configDiff,
}: {
  study: AndroidStudySummary;
  configDiff?: ConfigDiff;
}) {
  const rejoined = study.last_rejoin_at != null;

  return (
    <section className="rounded-3xl border border-wire bg-card p-5 shadow-card backdrop-blur-xl">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="text-[15px] font-bold text-ink">Study status</h2>
        <div className="flex flex-wrap gap-1.5">
          <EnrollmentBadge status={study.enrollment_status} />
          {configDiff ? (
            <ConfigBadge
              status={configDiff.config_status}
              diffCount={configDiff.diff_count}
            />
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
        <Field
          label="last study event"
          value={study.last_study_event ?? "—"}
          title={study.last_study_event ?? undefined}
        />
        <Field label="event time" value={relativeAge(study.last_study_event_at)} />
        <Field label="joined" value={relativeAge(study.last_join_at)} />
        {study.last_exit_at != null ? (
          <Field label="left" value={relativeAge(study.last_exit_at)} />
        ) : null}
        <Field
          label="config version"
          value={isoDateTime(study.config_updated_at)}
          title={study.config_id ?? undefined}
        />
        <Field
          label="events"
          value={
            study.duplicate_row_count > 0
              ? `${study.event_count} (${study.duplicate_row_count} duplicate rows)`
              : String(study.event_count)
          }
        />
      </div>

      {rejoined ? (
        <div className="mt-3 rounded-xl border border-wire bg-card-strong/70 px-3 py-2 text-[12px]">
          <span className="font-semibold text-ink">
            Rejoined {relativeAge(study.last_rejoin_at)}
          </span>
          {study.last_rejoin_pause_ms != null ? (
            <span className="text-sage">
              {" "}
              · collection was paused {durationLabel(study.last_rejoin_pause_ms)}{" "}
              beforehand
            </span>
          ) : (
            <span className="text-sage">
              {" "}
              · length of the pause before it is unknown
            </span>
          )}
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <div className="mb-1.5 text-[10px] uppercase tracking-[0.5px] text-sage">
            Approved consent
          </div>
          <ConsentChips
            consents={study.approved_consents}
            tone="teal"
            emptyLabel="None approved"
          />
        </div>
        <div>
          <div className="mb-1.5 text-[10px] uppercase tracking-[0.5px] text-sage">
            Declined consent
          </div>
          <ConsentChips
            consents={study.declined_consents}
            tone="red"
            emptyLabel="None declined"
          />
        </div>
      </div>

      {study.last_consent_at != null ? (
        <p className="mt-2 text-[11px] text-sage">
          Last consent {relativeAge(study.last_consent_at)}
          {study.consent_context === "study_update"
            ? " (during a study update)"
            : study.consent_context === "initial"
              ? " (initial enrolment)"
              : ""}
        </p>
      ) : null}
    </section>
  );
}
