import type { AndroidStudyEvent, StudyEventKind } from "../types";
import { absoluteTime, relativeAge } from "../utils/time";

const KIND_META: Record<StudyEventKind, { label: string; dot: string }> = {
  joined: { label: "Joined the study", dot: "bg-teal" },
  rejoined: { label: "Rejoined the study", dot: "bg-teal" },
  updated: { label: "Study updated", dot: "bg-amber-400" },
  consent: { label: "Consent recorded", dot: "bg-sky-400" },
  left: { label: "Quit the study", dot: "bg-red-500" },
  // An event kind the server did not recognise stays visible with its own text,
  // so a new Android client event type is never silently dropped.
  other: { label: "Other study event", dot: "bg-sage" },
};

function ConsentSummary({ event }: { event: AndroidStudyEvent }) {
  const parts: string[] = [];
  if (event.approved_consents.length > 0) {
    parts.push(`approved ${event.approved_consents.join(", ")}`);
  }
  if (event.declined_consents.length > 0) {
    parts.push(`declined ${event.declined_consents.join(", ")}`);
  }
  if (parts.length === 0) return null;
  return <span className="text-sage"> · {parts.join("; ")}</span>;
}

/**
 * The phone's study log, newest first and already deduplicated server-side.
 *
 * Unknown messages surface as "Other study event" with the original text intact
 * rather than being hidden, so a new client event is visible even before the
 * server learns to classify it.
 */
export default function StudyEventsTimeline({
  events,
}: {
  events: AndroidStudyEvent[];
}) {
  if (events.length === 0) {
    return (
      <section className="rounded-3xl border border-wire bg-card p-5 shadow-card backdrop-blur-xl">
        <h2 className="mb-2 text-[15px] font-bold text-ink">Study events</h2>
        <p className="text-[13px] text-sage">
          This phone has not reported any study events.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-3xl border border-wire bg-card p-5 shadow-card backdrop-blur-xl">
      <h2 className="mb-4 text-[15px] font-bold text-ink">Study events</h2>
      <ol className="space-y-3">
        {events.map((event, index) => {
          const meta = KIND_META[event.kind];
          // message repeats across kinds, so pair it with the index for a key.
          return (
            <li
              key={`${index}:${event.timestamp ?? "no-time"}`}
              className="flex gap-3"
            >
              <span
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dot}`}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[13px] font-semibold text-ink">
                    {meta.label}
                  </span>
                  <span
                    className="text-[11px] text-sage"
                    title={absoluteTime(event.timestamp)}
                  >
                    {relativeAge(event.timestamp)}
                  </span>
                  {event.occurrences > 1 ? (
                    <span className="text-[11px] text-sage">
                      · ×{event.occurrences}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-[12px] text-sage wrap-break-word">
                  {event.message}
                  {event.kind === "consent" ? (
                    <ConsentSummary event={event} />
                  ) : null}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
