import { useEffect, useRef, useSyncExternalStore } from "react";

/**
 * The live channel, so a number on screen follows the study rather than a timer.
 *
 * **One socket for the whole page.** The API watches once and tells everyone, and
 * this mirrors that: readers subscribe to a module-level connection instead of
 * opening one each. It connects when the first reader appears and closes after the
 * last one leaves, so a page with nothing listening holds nothing open.
 *
 * **A change is a reason to refetch, not a number to add.** The counts on screen
 * come from cache-backed endpoints whose absolute values are the truth, and the
 * refresher recomputes them on its own schedule. Adding arriving rows to a local
 * total would drift from those caches, and a drifted number looks exactly like a
 * correct one. So a change says "ask again", and the answer stays the API's.
 *
 * **Silence is measured.** The API sends a heartbeat while a study is quiet, which
 * is what makes a quiet study distinguishable from a socket that died without the
 * browser noticing -- what a laptop returning from sleep leaves behind. Hearing
 * nothing at all for several heartbeats is treated as a dead connection.
 */

/** One sensor's arrival: the rows that reached the study since the last tick. */
export interface SensorChange {
  platform: string;
  sensor: string;
  device_id: string;
  records: number;
}

export type LiveState = "connecting" | "open" | "offline";

interface Reader {
  /** Rows arrived. The batch names every device and sensor involved. */
  changes: (changes: SensorChange[]) => void;
  /** This reader's picture cannot be trusted and needs fetching from scratch. */
  reload: () => void;
}

const PATH = "/api/live";

// The API sends at most one message per tick, so a phone delivering forty tables
// arrives as a few messages rather than forty. Refetching on each would still ask
// more of the API than the minute-long poll this replaces, so a burst is collected
// and the readers are told once.
const COALESCE_MS = 1500;

// Longer than several of the API's heartbeats. Reached only when the connection is
// gone, since a quiet study still heartbeats.
const SILENCE_MS = 50_000;

// Backoff for a server that is restarting or unreachable, so a browser left open
// overnight is not asking every second by morning.
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 15_000, 30_000];

// A reader leaving is given a moment before the connection goes, because leaving
// and arriving in the same instant is ordinary: React remounts effects, and moving
// between two pages that both listen hands the channel from one to the other.
const HANDOVER_MS = 250;

// How often a reader asks anyway. The channel is what makes a number current, so
// while it is open the poll is only there to catch what a missed message would
// leave stale; with the channel down it carries the page on its own.
export const POLL_WITH_CHANNEL_MS = 300_000;
export const POLL_WITHOUT_CHANNEL_MS = 60_000;

const readers = new Set<Reader>();
const stateWatchers = new Set<() => void>();

let socket: WebSocket | null = null;
let state: LiveState = "offline";
/** The newest sequence seen, so a reconnect resumes rather than starts over. */
let lastSeq: number | null = null;
let attempt = 0;
let reconnectTimer: number | null = null;
let silenceTimer: number | null = null;
let coalesceTimer: number | null = null;
let handoverTimer: number | null = null;
let pending: SensorChange[] = [];

function announce(next: LiveState) {
  if (state === next) return;
  state = next;
  stateWatchers.forEach((notify) => notify());
}

function clearTimer(id: number | null) {
  if (id !== null) window.clearTimeout(id);
  return null;
}

function flush() {
  coalesceTimer = null;
  if (pending.length === 0) return;
  const batch = pending;
  pending = [];
  readers.forEach((reader) => reader.changes(batch));
}

function reloadEveryone() {
  readers.forEach((reader) => reader.reload());
}

/** Restart the clock that decides the connection has gone quiet for good. */
function armSilence() {
  silenceTimer = clearTimer(silenceTimer);
  silenceTimer = window.setTimeout(() => {
    // Closing rather than reopening directly: the close handler is what schedules
    // the next attempt, so both paths back to a connection are the same one.
    socket?.close();
  }, SILENCE_MS);
}

interface Message {
  type: string;
  seq?: number;
  refetch?: boolean;
  changes?: SensorChange[];
}

function handle(message: Message) {
  // A heartbeat carries the sequence it has not consumed, so reading it here keeps
  // a resume pointing at the last change rather than past it.
  if (typeof message.seq === "number") lastSeq = message.seq;

  if (message.type === "hello") {
    // The gap was longer than the history the API keeps, so nothing on screen can
    // be caught up a change at a time.
    if (message.refetch) reloadEveryone();
    return;
  }
  if (message.type === "refetch") {
    reloadEveryone();
    return;
  }
  if (message.type === "changes" && message.changes?.length) {
    pending.push(...message.changes);
    if (coalesceTimer === null) {
      coalesceTimer = window.setTimeout(flush, COALESCE_MS);
    }
  }
}

function scheduleReconnect() {
  if (readers.size === 0 || reconnectTimer !== null) return;
  const wait = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
  attempt += 1;
  // Jitter, so several tabs reopened by the same restart do not arrive together.
  reconnectTimer = window.setTimeout(
    () => {
      reconnectTimer = null;
      open();
    },
    wait + Math.random() * 500,
  );
}

function open() {
  if (socket !== null || readers.size === 0) return;

  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const resume = lastSeq === null ? "" : `?since=${lastSeq}`;
  const ws = new WebSocket(`${scheme}//${window.location.host}${PATH}${resume}`);
  socket = ws;
  announce("connecting");

  ws.onopen = () => {
    attempt = 0;
    announce("open");
    armSilence();
  };

  ws.onmessage = (event) => {
    armSilence();
    try {
      handle(JSON.parse(String(event.data)) as Message);
    } catch {
      // A message this version cannot read is not a reason to drop the channel.
    }
  };

  ws.onclose = () => {
    // Only the connection still in use reconnects. A shutdown clears `socket`
    // first, so the close it causes lands here and stops -- which is what keeps a
    // deliberate close from reopening itself.
    if (socket !== ws) return;
    socket = null;
    silenceTimer = clearTimer(silenceTimer);
    announce("offline");
    scheduleReconnect();
  };

  // A refused handshake arrives here and then as a close, which is where the retry
  // is decided. A session that has expired refuses every attempt; the reader's
  // fallback poll is what meets the redirect to the login page.
  ws.onerror = () => {};
}

function shutdown() {
  reconnectTimer = clearTimer(reconnectTimer);
  silenceTimer = clearTimer(silenceTimer);
  coalesceTimer = clearTimer(coalesceTimer);
  pending = [];
  const closing = socket;
  socket = null;
  closing?.close();
  announce("offline");
}

function subscribe(reader: Reader): () => void {
  handoverTimer = clearTimer(handoverTimer);
  readers.add(reader);
  if (readers.size === 1) open();
  return () => {
    readers.delete(reader);
    if (readers.size > 0) return;
    handoverTimer = window.setTimeout(() => {
      handoverTimer = null;
      if (readers.size === 0) shutdown();
    }, HANDOVER_MS);
  };
}

function watchState(notify: () => void): () => void {
  stateWatchers.add(notify);
  return () => stateWatchers.delete(notify);
}

/**
 * Whether the channel is carrying changes right now.
 *
 * Read through an external store rather than kept in component state: the
 * connection lives outside React, which is what lets a reader lengthen its
 * fallback poll while the channel is open without a render deciding anything.
 */
export function useLiveState(): LiveState {
  return useSyncExternalStore(
    watchState,
    () => state,
    () => "offline" as LiveState,
  );
}

/**
 * Run something whenever rows arrive, and nothing else.
 *
 * For a reader that already knows when to fetch -- one keyed on what is on screen
 * -- and needs only to be told that there is something new to fetch. It does not
 * fetch on mount, so a reader that loads on its own is not made to load twice.
 *
 * A reload signal calls it too: both mean the picture on screen may no longer be
 * the study's.
 */
export function useLiveChanges(onArrival: () => void): void {
  const latest = useRef(onArrival);

  useEffect(() => {
    latest.current = onArrival;
  });

  useEffect(
    () =>
      subscribe({
        changes: () => latest.current(),
        reload: () => latest.current(),
      }),
    [],
  );
}

/**
 * Keep one reader current: load it, refetch when rows arrive, ask again on a timer.
 *
 * The first fetch belongs here rather than in a reader's own effect. `load` is the
 * one answer to "what should this show", whether it is being asked for the first
 * time, because rows arrived, or because the timer came round.
 *
 * `load` runs for a change naming `device` -- or for any change when that is
 * absent, which is what a page counting the whole study wants. A page showing one
 * phone stays still while a different phone uploads.
 *
 * The poll is kept even with the channel open, at a long interval. A socket that
 * has quietly stopped delivering looks exactly like a study where nothing is
 * happening, so a page whose only source of numbers had failed would leave a
 * researcher with no way to tell.
 */
export function useLiveRefresh(
  load: () => void,
  device?: string | null,
): LiveState {
  const channel = useLiveState();
  const latest = useRef(load);
  const target = useRef(device);

  // Every render, so a reader rebuilding `load` each time is still the one that
  // runs. Nothing here re-renders, and nothing downstream depends on its identity
  // -- which is what frees a reader from having to memoize it.
  useEffect(() => {
    latest.current = load;
    target.current = device;
  });

  // Fetching is driven by the subject rather than by the callback: on mount, and
  // again when the reader turns to a different phone.
  useEffect(() => {
    latest.current();
  }, [device]);

  useEffect(
    () =>
      subscribe({
        changes: (changes) => {
          const wanted = target.current;
          if (wanted && !changes.some((c) => c.device_id === wanted)) return;
          latest.current();
        },
        reload: () => latest.current(),
      }),
    [],
  );

  const every =
    channel === "open" ? POLL_WITH_CHANNEL_MS : POLL_WITHOUT_CHANNEL_MS;
  useEffect(() => {
    const id = window.setInterval(() => latest.current(), every);
    return () => window.clearInterval(id);
  }, [every]);

  return channel;
}
