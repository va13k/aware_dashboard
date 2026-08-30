import { useEffect, useState } from "react";
import {
  fetchDeviceMessages,
  type DeviceMessages,
  type DevicePrompt,
} from "../api/client";

function when(ms: number | null): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

/** How long the participant took, for a prompt they answered. */
function took(prompt: DevicePrompt): string {
  if (!prompt.answered || !prompt.answered_at) return "";
  const seconds = Math.max(0, Math.round((prompt.answered_at - prompt.shown_at) / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.round(seconds / 60)}m`;
}



/**
 * What became of a prompt nobody answered, in the client's own words.
 *
 * Read from com.aware.ESM: 0 new, 1 dismissed, 2 answered, 3 expired, 4 visible,
 * 5 branched, 6 replaced. The distinction the study needs is between a
 * participant who chose not to answer and a prompt they never got the chance to:
 * replaced means the next one arrived first and wiped this one off the screen.
 */
const OUTCOME: Record<number, string> = {
  0: "waiting",
  1: "dismissed",
  3: "expired",
  4: "on screen",
  5: "branched",
  6: "replaced by a later one",
};

/** The prompts as a spreadsheet, answered and unanswered alike. */
function asCsv(prompts: DevicePrompt[]): string {
  const cell = (value: unknown) => {
    const text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const header = [
    "shown_at",
    "question",
    "instructions",
    "trigger",
    "answered",
    "answer",
    "answered_at",
    "status",
  ];
  const lines = prompts.map((p) =>
    [
      new Date(p.shown_at).toISOString(),
      p.title,
      p.instructions,
      p.trigger_name,
      p.answered ? "yes" : "no",
      p.answer,
      p.answered_at ? new Date(p.answered_at).toISOString() : "",
      p.status,
    ]
      .map(cell)
      .join(","),
  );
  return [header.join(","), ...lines].join("\n");
}

/**
 * What one participant was asked and what they answered.
 *
 * Two sections rather than one table, because only one of the two has an answer
 * to show. A notice is rendered by the client as a notification and recorded
 * nowhere, and sync and update are acted on silently, so a row pairing any of
 * them with a blank answer would read as a participant who ignored it.
 */
export default function DeviceMessagesModal({
  deviceId,
  title,
  onClose,
}: {
  deviceId: string;
  title?: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<DeviceMessages | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let live = true;
    fetchDeviceMessages(deviceId)
      .then((result) => live && setData(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [deviceId]);

  const prompts = data?.prompts ?? [];
  const answered = prompts.filter((p) => p.answered).length;
  // Worth calling out separately: these are not participants who ignored a
  // question, they are questions that were taken off the screen by the next one.
  const replaced = prompts.filter((p) => !p.answered && p.status === 6).length;
  const silent = (data?.sent ?? []).filter((s) => s.kind !== "question");

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="my-6 flex max-h-[88vh] w-full max-w-4xl flex-col rounded-3xl border border-wire bg-card p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[16px] font-bold text-ink">Prompts and answers</h2>
            {title ? <p className="text-[12px] text-sage">{title}</p> : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {prompts.length > 0 ? (
              <a
                href={URL.createObjectURL(
                  new Blob([asCsv(prompts)], { type: "text/csv" }),
                )}
                download={`prompts-${deviceId.slice(0, 12)}.csv`}
                className="cursor-pointer rounded-full border border-wire px-3 py-1 text-[12px] text-sage hover:border-teal hover:text-ink"
              >
                Download CSV
              </a>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="cursor-pointer rounded-full border border-wire px-3 py-1 text-[12px] text-sage hover:border-teal hover:text-ink"
            >
              Close
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {failed ? (
            <p className="text-[13px] text-sage">
              This participant's prompts could not be read.
            </p>
          ) : !data ? (
            <p className="text-[13px] text-sage">Reading…</p>
          ) : (
            <>
              <p className="mb-3 text-[12px] text-sage">
                {prompts.length === 0
                  ? "No prompt has reached this participant yet."
                  : `${answered} of ${prompts.length} answered` +
                    (replaced > 0
                      ? `, ${replaced} replaced before they could be`
                      : "") +
                    "."}
              </p>

              {prompts.map((prompt) => (
                <div
                  key={`${prompt.shown_at}-${prompt.title}`}
                  className="mb-2 rounded-2xl border border-wire p-3"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[14px] font-semibold text-ink">
                      {prompt.title || "(untitled)"}
                    </span>
                    <span className="shrink-0 text-[11px] text-sage">
                      {prompt.trigger_name === "dashboard"
                        ? "sent from here"
                        : prompt.trigger_name || "schedule"}
                    </span>
                  </div>
                  {prompt.instructions ? (
                    <p className="mt-0.5 text-[12px] text-sage">{prompt.instructions}</p>
                  ) : null}
                  <p className="mt-1.5 text-[13px]">
                    {prompt.answered ? (
                      <>
                        <span className="font-semibold text-ink">{prompt.answer}</span>
                        <span className="text-sage">
                          {" "}
                          — answered {when(prompt.answered_at)}
                          {took(prompt) ? `, ${took(prompt)} after it appeared` : ""}
                        </span>
                      </>
                    ) : (
                      <span className="text-sage">
                        Shown {when(prompt.shown_at)} —{" "}
                        {OUTCOME[prompt.status] ?? "not answered"}.
                      </span>
                    )}
                  </p>
                </div>
              ))}

              {silent.length > 0 ? (
                <>
                  <h3 className="mt-5 text-[14px] font-semibold text-ink">
                    Also sent to this phone
                  </h3>
                  <p className="mb-2 text-[12px] text-sage">
                    Nothing comes back from these. A notice is shown as a
                    notification and recorded nowhere; a sync or an update is
                    carried out without the participant seeing anything.
                  </p>
                  {silent.map((row) => (
                    <div
                      key={row._id}
                      className="mb-1.5 flex items-baseline justify-between gap-3 rounded-xl border border-wire px-3 py-2"
                    >
                      <span className="text-[13px] text-ink">
                        {row.kind}
                        {row.title ? ` — ${row.title}` : ""}
                        {!row.retained && row.kind === "notice" ? (
                          <span className="text-sage"> (words not kept)</span>
                        ) : null}
                      </span>
                      <span className="shrink-0 text-[11px] text-sage">
                        {when(row.sent_at)}
                      </span>
                    </div>
                  ))}
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
