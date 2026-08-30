import { useEffect, useMemo, useState } from "react";
import DeviceList from "../components/DeviceList";
import ComposeMessageDialog from "../components/ComposeMessageDialog";
import {
  fetchDevices,
  fetchMessageHistory,
  sendMessage,
  type MessageHistory,
  type SendMessageRequest,
} from "../api/client";
import type { Device, DevicesResponse } from "../types";
import { deviceLabel } from "../utils/devices";

/**
 * Reaching participants, and what became of it.
 *
 * Every other page here reads what a phone sent. This one sends, and that shapes
 * two things.
 *
 * Recipients are chosen from the same list the Devices tab shows, not from a
 * dropdown of identifiers. A researcher deciding who to interrupt needs to see who
 * they are and how they are doing — a phone that withdrew, or has not reported in a
 * week, is one you would think twice about prompting, and a bare UUID hides that.
 * The list carries its own filters, so "everyone still enrolled" is a filter and a
 * tick rather than a group somebody has to maintain.
 *
 * What is sent is settled in a dialog rather than in a panel beside the list.
 * Sending interrupts somebody, and the last question it asks — whether the words are
 * kept with the study record — is a decision, not a setting. A checkbox on a form is
 * read past; a dialog that has to be answered is not.
 *
 * The three states below are kept apart deliberately. *Sent* is ours. *Delivered* is
 * the phone's own record of receiving it, uploaded with the rest of its data, which
 * makes it evidence rather than an assumption — and which lags a sync. A prompt to a
 * quiet phone sits at "sent" until it next uploads, and that is a normal state, not
 * a failure.
 */

function when(ms: number): string {
  return new Date(ms).toLocaleString();
}

export default function MessagesPage() {
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [composing, setComposing] = useState(false);
  const [history, setHistory] = useState<MessageHistory | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  useEffect(() => {
    fetchDevices()
      .then(setDevices)
      .catch(() => setDevices({ android: [], ios: [] }));
  }, []);

  // Only Android phones subscribe: an iPhone keeps its study state locally and
  // listens on nothing, so there is no topic to address one on.
  const reachable = useMemo(() => devices?.android ?? [], [devices]);

  const loadHistory = async () => {
    try {
      setHistory(await fetchMessageHistory());
    } catch {
      setHistory(null);
    }
  };

  useEffect(() => {
    let current = true;
    fetchMessageHistory()
      .then((next) => current && setHistory(next))
      .catch(() => current && setHistory(null));
    return () => {
      current = false;
    };
  }, []);

  function toggle(device: Device) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(device.device_id)) next.delete(device.device_id);
      else next.add(device.device_id);
      return next;
    });
  }

  async function send(body: Omit<SendMessageRequest, "device_id">) {
    const targets = [...picked];
    // One request carrying every recipient. The server publishes per phone either
    // way — the clients subscribe only to their own topics — but doing the fan-out
    // there keeps the rate limit, the record and the answer in one transaction,
    // where a request per phone leaves a half-sent state if one of them fails.
    try {
      const answer = await sendMessage({ ...body, device_ids: targets });
      const parts = [`Sent to ${answer.sent.length} of ${targets.length}.`];
      if (answer.held.length) {
        parts.push(`${answer.held.length} held by the rate limit.`);
      }
      if (answer.failed.length) {
        parts.push(`${answer.failed.length} could not be sent.`);
      }
      if (body.retain === false && answer.sent.length) {
        parts.push("The words were not kept with the study record.");
      }
      setResult({ ok: answer.sent.length > 0, text: parts.join(" ") });
    } catch (error) {
      setResult({ ok: false, text: (error as Error).message });
    }
    setComposing(false);
    await loadHistory();
  }

  const chosen = reachable.filter((device) => picked.has(device.device_id));

  // Who a row belongs to. The three columns list every device at once, so the
  // same question answered by two participants reads as one asked twice without
  // it. The id rather than the name the device list shows: that one falls back to
  // the make and model, and two participants issued the same handset are then one
  // name -- which is the case this label exists to tell apart.
  const who = (deviceId: string): string => deviceId.slice(0, 12);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-ink mb-1">Messages</h1>
      <p className="text-sage text-sm mb-6 max-w-3xl">
        The one thing this system does outward. Choose who to reach, then what to
        send. Sending is an intervention rather than an observation, so it is rate
        limited per phone and every send is recorded.
      </p>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <DeviceList
          devices={devices}
          selected={null}
          onSelect={toggle}
          pickedIds={picked}
          header={(visible) => {
            const reachableVisible = visible.filter(
              (device) => device.platform === "android",
            );
            const allPicked =
              reachableVisible.length > 0 &&
              reachableVisible.every((device) => picked.has(device.device_id));
            return (
              <div className="flex flex-wrap items-center gap-3 text-[13px]">
                <button
                  type="button"
                  onClick={() =>
                    setPicked((current) => {
                      const next = new Set(current);
                      reachableVisible.forEach((device) =>
                        allPicked
                          ? next.delete(device.device_id)
                          : next.add(device.device_id),
                      );
                      return next;
                    })
                  }
                  disabled={reachableVisible.length === 0}
                  className="cursor-pointer rounded-lg border border-wire bg-card-strong px-3 py-1.5 font-medium text-ink transition-colors hover:bg-teal-soft/50 disabled:opacity-40"
                >
                  {allPicked
                    ? `Clear these ${reachableVisible.length}`
                    : `Choose these ${reachableVisible.length}`}
                </button>
                <span className="text-sage">
                  {picked.size === 0
                    ? "Nobody chosen yet"
                    : `${picked.size} chosen`}
                </span>
                {visible.length !== reachableVisible.length ? (
                  <span className="text-sage">
                    iPhones cannot be messaged and are not counted
                  </span>
                ) : null}
              </div>
            );
          }}
        />

        <aside className="min-w-0">
          <div className="rounded-2xl border border-wire bg-card-strong p-4">
            <h2 className="text-sm font-semibold text-ink">Recipients</h2>
            {chosen.length === 0 ? (
              <p className="mt-2 text-[13px] text-sage">
                Pick phones on the left. The filters above the list are the quickest
                way to reach a group — everyone still enrolled, or everyone gone
                quiet.
              </p>
            ) : (
              <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto">
                {chosen.map((device) => (
                  <li
                    key={device.device_id}
                    className="truncate text-[13px] text-ink"
                    title={device.device_id}
                  >
                    {deviceLabel(device)}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={() => setComposing(true)}
              disabled={chosen.length === 0}
              className="mt-4 w-full cursor-pointer rounded-lg border-none bg-teal px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              Compose a message
            </button>
            {result ? (
              <p
                className={`mt-3 text-[13px] ${result.ok ? "text-teal" : "text-red-600"}`}
              >
                {result.text}
              </p>
            ) : null}
          </div>

          <Column
            title="Sent"
            note="What was asked of a phone"
            rows={(history?.sent ?? []).map((m) => ({
              key: `s${m._id}`,
              head: m.kind === "sync" ? "Upload request" : m.title || "(not kept)",
              sub:
                `${who(m.device_id)} · ${when(m.sent_at)}` +
                (m.retained ? "" : " · words not kept"),
            }))}
          />
          <Column
            title="Delivered"
            note="What a phone recorded receiving. Reported on its next upload, so a quiet phone lags."
            rows={(history?.delivered ?? []).map((m, i) => ({
              key: `d${i}`,
              head: m.topic.split("/").pop() ?? m.topic,
              sub: `${who(m.device_id)} · ${when(m.timestamp)}`,
            }))}
          />
          <Column
            title="Answered"
            note="What came back"
            rows={(history?.answered ?? []).map((m, i) => ({
              key: `a${i}`,
              head: m.esm_user_answer || "(no answer)",
              sub: `${who(m.device_id)} · ${m.esm_title} · ${when(m.answered_at)}`,
            }))}
          />
        </aside>
      </div>

      {composing ? (
        <ComposeMessageDialog
          recipients={chosen.map(deviceLabel)}
          onCancel={() => setComposing(false)}
          onSend={send}
        />
      ) : null}
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
    <div className="mt-4 rounded-2xl border border-wire bg-card-strong p-4">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      <p className="mb-2 text-[11px] leading-snug text-sage">{note}</p>
      {rows.length === 0 ? (
        <p className="text-[12px] italic text-sage">Nothing yet</p>
      ) : (
        rows.slice(0, 6).map((r) => (
          <div key={r.key} className="border-t border-wire/60 py-2">
            <p className="text-[13px] leading-snug text-ink">{r.head}</p>
            <p className="text-[11px] text-sage">{r.sub}</p>
          </div>
        ))
      )}
    </div>
  );
}
