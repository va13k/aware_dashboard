import { useEffect, useRef, useState } from "react";
import type { SendMessageRequest } from "../api/client";

/**
 * What to send, and whether it enters the study record.
 *
 * A dialog rather than a panel because sending interrupts people. The recipients
 * are named at the top so the count is confirmed at the moment of sending rather
 * than remembered from a list somewhere else, and the last question — whether the
 * words are kept — is asked as a question with two answers instead of offered as a
 * checkbox. A checkbox is read past; this is not.
 */

type Kind = "sync" | "update" | "question" | "esm" | "notice";

const KINDS: { value: Kind; label: string; hint: string }[] = [
  {
    value: "question",
    label: "Ask a question",
    hint: "Waits on the phone until it is answered. Use it for anything outside the protocol — a check on a quiet phone, a one-off ask.",
  },
  {
    value: "esm",
    label: "Ask about this moment (ESM)",
    hint: "Expires if it is not answered in time, because an answer given hours late describes a different moment. Use it for what the study is measuring.",
  },
  {
    value: "notice",
    label: "Tell them something",
    hint: "A notification and nothing else — no answer is asked for and none is recorded.",
  },
  {
    value: "sync",
    label: "Ask the phone to upload",
    hint: "Costs the participant nothing and shows them nothing. Use it when a phone has gone quiet and you want to know whether it is holding data.",
  },
  {
    value: "update",
    label: "Ask the phone for a study update",
    hint: "Makes the phone re-read the study configuration now instead of waiting on its own timer. Send this after changing questions, schedules or sensors.",
  },
];

export default function ComposeMessageDialog({
  recipients,
  onCancel,
  onSend,
}: {
  recipients: string[];
  onCancel: () => void;
  onSend: (body: Omit<SendMessageRequest, "device_id">) => Promise<void>;
}) {
  const [kind, setKind] = useState<Kind>("question");
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [answers, setAnswers] = useState("Yes, No");
  const [expires, setExpires] = useState(1800);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    first.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onCancel]);

  // Only a composed message has words to keep. A sync or an update carries none, so
  // the question would have nothing to be about and is not asked.
  const composed = kind === "question" || kind === "esm" || kind === "notice";
  // Only a question has answers to offer, and only a timed one expires.
  const wantsAnswer = kind === "question" || kind === "esm";
  const ready = !composed || title.trim().length > 0;

  async function submit(retain: boolean) {
    setBusy(true);
    try {
      await onSend({
        kind,
        retain,
        expires,
        ...(composed
          ? {
              title,
              instructions,
              answers: answers
                .split(",")
                .map((a) => a.trim())
                .filter(Boolean),
            }
          : {}),
      });
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-wire bg-card-strong px-3 py-2 text-sm text-ink";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Compose a message"
      onClick={(event) => event.target === event.currentTarget && onCancel()}
    >
      {/* `card` carries an alpha of its own, which is right for a panel resting on
          the page and wrong for one over a dimmed backdrop: the darkening shows
          through and the dialog reads as half-erased. `card-strong` is the opaque
          one, and the blur above is what the other dialogs put behind theirs. */}
      <div className="my-auto w-full max-w-lg rounded-2xl border border-wire bg-card-strong p-5 shadow-xl">
        {asking ? (
          <>
            <h2 className="text-lg font-semibold text-ink">
              Keep this message with the study record?
            </h2>
            <p className="mt-2 text-[13px] leading-snug text-sage">
              Keeping it stores what you wrote alongside the study&apos;s data, where
              it can be read back later and exported with everything else.
            </p>
            <p className="mt-2 text-[13px] leading-snug text-sage">
              Not keeping it stores only that something was sent to these phones, and
              when. Use that for anything operational — a reminder to charge the
              phone — that is not part of what the study is measuring.
            </p>
            <p className="mt-2 text-[12px] leading-snug text-sage">
              Either way the send itself is recorded: it is what the rate limit counts,
              and a message to a participant should leave a trace.
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setAsking(false)}
                disabled={busy}
                className="cursor-pointer rounded-lg border border-wire bg-card-strong px-4 py-2 text-sm text-ink disabled:opacity-40"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => submit(false)}
                disabled={busy}
                className="cursor-pointer rounded-lg border border-wire bg-card-strong px-4 py-2 text-sm font-medium text-ink disabled:opacity-40"
              >
                Send without keeping
              </button>
              <button
                type="button"
                onClick={() => submit(true)}
                disabled={busy}
                className="cursor-pointer rounded-lg border-none bg-teal px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy ? "Sending…" : "Keep and send"}
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-ink">Compose a message</h2>
            <p className="mt-1 text-[13px] text-sage">
              To {recipients.length} phone{recipients.length === 1 ? "" : "s"}:{" "}
              <span className="text-ink">
                {recipients.slice(0, 3).join(", ")}
                {recipients.length > 3 ? ` and ${recipients.length - 3} more` : ""}
              </span>
            </p>

            <label className="mt-4 block text-sm font-medium text-ink">
              What to send
            </label>
            <select
              ref={first}
              value={kind}
              onChange={(event) => setKind(event.target.value as Kind)}
              className={`mt-1 ${field}`}
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[12px] leading-snug text-sage">
              {KINDS.find((k) => k.value === kind)?.hint}
            </p>

            {composed ? (
              <>
                <label className="mt-4 block text-sm font-medium text-ink">
                  Title
                </label>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="How is your day going?"
                  className={`mt-1 ${field}`}
                />
                <label className="mt-3 block text-sm font-medium text-ink">
                  Instructions
                </label>
                <input
                  value={instructions}
                  onChange={(event) => setInstructions(event.target.value)}
                  placeholder="One touch answer"
                  className={`mt-1 ${field}`}
                />
                {wantsAnswer ? (
                  <>
                    <label className="mt-3 block text-sm font-medium text-ink">
                      Answers, comma separated
                    </label>
                    <input
                      value={answers}
                      onChange={(event) => setAnswers(event.target.value)}
                      className={`mt-1 ${field}`}
                    />
                    <p className="mt-1 text-[12px] text-sage">
                      Leave empty for a free-text answer.
                    </p>
                  </>
                ) : (
                  <p className="mt-3 text-[12px] leading-snug text-sage">
                    Nothing is asked of the participant: this arrives as a
                    notification with the words above and no way to reply, so
                    there is no answer to record.
                  </p>
                )}

                {kind === "esm" ? (
                  <>
                    <label className="mt-3 block text-sm font-medium text-ink">
                      Expires after
                    </label>
                    <select
                      value={expires}
                      onChange={(event) => setExpires(Number(event.target.value))}
                      className={`mt-1 ${field}`}
                    >
                      <option value={900}>15 minutes</option>
                      <option value={1800}>30 minutes</option>
                      <option value={3600}>1 hour</option>
                      <option value={10800}>3 hours</option>
                    </select>
                    <p className="mt-1 text-[12px] leading-snug text-sage">
                      Unanswered after this, it is recorded as expired rather
                      than left waiting — a reading not taken, which is what a
                      momentary question needs to say.
                    </p>
                  </>
                ) : null}
              </>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={onCancel}
                className="cursor-pointer rounded-lg border border-wire bg-card-strong px-4 py-2 text-sm text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => (composed ? setAsking(true) : submit(true))}
                disabled={!ready || busy}
                className="cursor-pointer rounded-lg border-none bg-teal px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {composed ? "Continue" : busy ? "Sending…" : "Send"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
