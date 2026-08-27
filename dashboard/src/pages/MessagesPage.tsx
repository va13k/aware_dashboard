import { useCallback, useEffect, useState } from "react";
import {
  fetchDevices,
  fetchMessageHistory,
  sendMessage,
  type MessageHistory,
  type SendMessageRequest,
} from "../api/client";

/**
 * Reaching a participant, and what became of it.
 *
 * Every other page here reads what a phone sent. This one sends, and the difference
 * shapes it: a prompt interrupts somebody, so what it will look like and who it goes
 * to are settled before the button, and what happened to it is shown afterwards
 * rather than assumed.
 *
 * The three states are kept apart deliberately. *Sent* is ours. *Delivered* is the
 * phone's own record of receiving it, uploaded with the rest of its data — which is
 * evidence rather than an assumption, and which lags a sync. A prompt to a quiet
 * phone sits at "sent" until that phone next uploads, and that is a normal state,
 * not a failure, so it is drawn as waiting rather than as an error.
 */

type Kind = "sync" | "update" | "question" | "notice";

// Addresses every phone the study log recorded joining.
const ALL_DEVICES = "all";

const KINDS: { value: Kind; label: string; hint: string }[] = [
  {
    value: "sync",
    label: "Ask the phone to upload",
    hint: "Costs the participant nothing and shows them nothing. Use it when a phone has gone quiet and you want to know whether it is holding data.",
  },
  {
    value: "update",
    label: "Ask the phone for a study update",
    hint: "Makes the phone re-read the study configuration now instead of waiting on its own timer. Send this to everyone after changing questions, schedules or sensors — otherwise each phone picks the change up whenever it happens to look.",
  },
  {
    value: "question",
    label: "Ask a question",
    hint: "Appears on the phone now. The answer lands in the study data alongside the scheduled questionnaires.",
  },
  {
    value: "notice",
    label: "Tell them something",
    hint: "A message with one button to dismiss it. Nothing is being asked.",
  },
];

function when(ms: number): string {
  return new Date(ms).toLocaleString();
}

export default function MessagesPage() {
  const [devices, setDevices] = useState<string[]>([]);
  const [device, setDevice] = useState("");
  const [kind, setKind] = useState<Kind>("question");
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [answers, setAnswers] = useState("Yes, No");
  const [retain, setRetain] = useState(true);
  const [history, setHistory] = useState<MessageHistory | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  const reload = useCallback(async (id: string) => {
    try {
      setHistory(await fetchMessageHistory(id || undefined));
    } catch {
      setHistory(null);
    }
  }, []);

  useEffect(() => {
    fetchDevices()
      .then((d) => {
        const ids = (d.android ?? []).map((x) => x.device_id);
        setDevices(ids);
        if (ids.length) setDevice(ids[0]);
      })
      .catch(() => setDevices([]));
  }, []);

  useEffect(() => {
    // Guarded rather than fired and forgotten: switching device twice quickly would
    // otherwise let the first answer land after the second and show the wrong
    // phone's history.
    let current = true;
    (async () => {
      try {
        const next = await fetchMessageHistory(device || undefined);
        if (current) setHistory(next);
      } catch {
        if (current) setHistory(null);
      }
    })();
    return () => {
      current = false;
    };
  }, [device]);

  async function send() {
    setBusy(true);
    setResult(null);
    const body: SendMessageRequest = { device_id: device, kind, retain };
    if (kind !== "sync") {
      body.title = title;
      body.instructions = instructions;
      body.answers = answers
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean);
    }
    try {
      const answer = await sendMessage(body);
      // A study-wide send rarely succeeds uniformly: a phone at its limit is held
      // and the rest go, so the count is the answer rather than the word "sent".
      const parts = [`Sent to ${answer.sent.length} phone(s).`];
      if (answer.held.length) {
        parts.push(`${answer.held.length} held by the rate limit.`);
      }
      if (answer.failed.length) {
        parts.push(`${answer.failed.length} could not be published.`);
      }
      if (composing && answer.retained === false) {
        parts.push("Its words were not kept.");
      }
      setResult({ ok: true, text: parts.join(" ") });
      await reload(device);
    } catch (error) {
      // A refusal by the rate limit arrives here too, and it is the message worth
      // reading: it says how many have gone and when the window lifts.
      setResult({ ok: false, text: (error as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const composing = kind !== "sync" && kind !== "update";
  const ready = device && (!composing || title.trim());

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold text-ink mb-1">Messages</h1>
      <p className="text-sage text-sm mb-6">
        The one thing this system does outward. Sending is an intervention
        rather than an observation, so it is rate limited per device and every
        send is recorded.
      </p>

      <div className="border border-mist rounded-xl p-5 mb-8">
        <label className="block text-sm font-medium text-ink mb-1">To</label>
        <select
          value={device}
          onChange={(e) => setDevice(e.target.value)}
          className="w-full mb-4 px-3 py-2 border border-mist rounded-lg text-sm"
        >
          <option value={ALL_DEVICES}>
            Every phone in the study ({devices.length})
          </option>
          {devices.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>

        <label className="block text-sm font-medium text-ink mb-1">
          What to send
        </label>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as Kind)}
          className="w-full px-3 py-2 border border-mist rounded-lg text-sm"
        >
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
        <p className="text-[12px] text-sage mt-1 mb-4">
          {KINDS.find((k) => k.value === kind)?.hint}
        </p>

        {composing && (
          <>
            <label className="block text-sm font-medium text-ink mb-1">
              Title
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="How is your day going?"
              className="w-full mb-3 px-3 py-2 border border-mist rounded-lg text-sm"
            />
            <label className="block text-sm font-medium text-ink mb-1">
              Instructions
            </label>
            <input
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="One touch answer"
              className="w-full mb-3 px-3 py-2 border border-mist rounded-lg text-sm"
            />
            <label className="block text-sm font-medium text-ink mb-1">
              Answers, comma separated
            </label>
            <input
              value={answers}
              onChange={(e) => setAnswers(e.target.value)}
              className="w-full mb-1 px-3 py-2 border border-mist rounded-lg text-sm"
            />
            <p className="text-[12px] text-sage mb-4">
              Leave empty for a free-text answer.
            </p>

            <label className="flex items-start gap-2 mb-4 cursor-pointer">
              <input
                type="checkbox"
                checked={retain}
                onChange={(e) => setRetain(e.target.checked)}
                className="mt-1"
              />
              <span className="text-[13px] text-ink">
                Keep this message in the database
              </span>
            </label>
          </>
        )}

        <button
          onClick={send}
          disabled={busy || !ready}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-teal text-white disabled:opacity-40 border-none cursor-pointer"
        >
          {busy ? "Sending…" : "Send"}
        </button>

        {result && (
          <p
            className={`mt-3 text-[13px] ${
              result.ok ? "text-teal" : "text-red-600"
            }`}
          >
            {result.text}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Column
          title="Sent"
          note="What was asked of the phone"
          rows={(history?.sent ?? []).map((m) => ({
            key: `s${m._id}`,
            head:
              m.kind === "sync" ? "Upload request" : m.title || "(not kept)",
            sub: when(m.sent_at) + (m.retained ? "" : " · words not kept"),
          }))}
        />
        <Column
          title="Delivered"
          note="What the phone recorded receiving. Reported on its next upload, so a quiet phone lags."
          rows={(history?.delivered ?? []).map((m, i) => ({
            key: `d${i}`,
            head: m.topic.split("/").pop() ?? m.topic,
            sub: when(m.timestamp),
          }))}
        />
        <Column
          title="Answered"
          note="What came back"
          rows={(history?.answered ?? []).map((m, i) => ({
            key: `a${i}`,
            head: m.esm_user_answer || "(no answer)",
            sub: `${m.esm_title} · ${when(m.answered_at)}`,
          }))}
        />
      </div>
    </div>
  );
}

function Column({
  title,
  note,
  rows,
}: {
  title: string;
  note: string;
  rows: { key: string; head: string; sub: string }[];
}) {
  return (
    <div className="border border-mist rounded-xl p-4">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      <p className="text-[11px] text-sage mb-3 leading-snug">{note}</p>
      {rows.length === 0 ? (
        <p className="text-[12px] text-sage italic">Nothing yet</p>
      ) : (
        rows.map((r) => (
          <div key={r.key} className="py-2 border-t border-mist/60">
            <p className="text-[13px] text-ink leading-snug">{r.head}</p>
            <p className="text-[11px] text-sage">{r.sub}</p>
          </div>
        ))
      )}
    </div>
  );
}
