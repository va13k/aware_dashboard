import { useSettledLiveState } from "../api/live";
import type { LiveState } from "../api/live";

/**
 * Whether the numbers on screen are following the study or a timer.
 *
 * Without this a dead channel and a quiet study look identical: both are a page
 * that simply does not change. The counts stay correct either way -- a reader falls
 * back to polling when the channel drops -- but "nothing is arriving" and "nothing
 * is reaching me" are different facts, and only one of them is about the study.
 *
 * The timing of what to draw belongs to the channel rather than here: a drop is
 * reported only once it has lasted, a recovery at once, and a socket closed because
 * no page is listening is not reported at all. This reads the settled answer and
 * gives it a colour.
 */

const LOOK: Record<
  LiveState,
  { dot: string; text: string; label: string; title: string }
> = {
  open: {
    dot: "bg-expected",
    text: "text-sage",
    label: "Live",
    title: "Connected. The page updates as data reaches the study.",
  },
  connecting: {
    dot: "bg-moderate animate-pulse",
    text: "text-sage",
    label: "Connecting",
    title:
      "Reopening the live channel. The page is refreshing on a timer meanwhile.",
  },
  offline: {
    dot: "bg-short",
    text: "text-amber-600 font-semibold",
    label: "Offline",
    title:
      "The live channel is down, so the page is refreshing every 60 seconds " +
      "instead. The numbers are still correct, just slower to arrive.",
  },
};

export default function LiveStatus() {
  const channel = useSettledLiveState();
  if (channel === null) return null;

  const look = LOOK[channel];
  return (
    <span
      role="status"
      aria-live="polite"
      title={look.title}
      className={`flex items-center gap-1.5 px-2.5 py-1 text-[13px] font-medium ${look.text}`}
    >
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${look.dot}`}
        aria-hidden="true"
      />
      {/* The dot alone carries the state where the header is tight. */}
      <span className="hidden sm:inline">{look.label}</span>
      <span className="sr-only">Live updates: {look.label}</span>
    </span>
  );
}
