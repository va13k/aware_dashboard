import type { SensorRecord } from "../types";
import { normalizeTimestamp } from "./time";

export type RangeKey = "1h" | "3h" | "1d" | "1w" | "1m" | "all";

export interface RangePreset {
  key: RangeKey;
  /** Short label for the control. */
  label: string;
  /** Window length in ms, or null for "all time". */
  ms: number | null;
}

export const RANGE_PRESETS: RangePreset[] = [
  { key: "1h", label: "1h", ms: 60 * 60 * 1000 },
  { key: "3h", label: "3h", ms: 3 * 60 * 60 * 1000 },
  { key: "1d", label: "24h", ms: 24 * 60 * 60 * 1000 },
  { key: "1w", label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
  { key: "1m", label: "30d", ms: 30 * 24 * 60 * 60 * 1000 },
  { key: "all", label: "All", ms: null },
];

export const DEFAULT_RANGE: RangeKey = "1h";

export function rangePreset(key: RangeKey): RangePreset {
  return RANGE_PRESETS.find((r) => r.key === key) ?? RANGE_PRESETS[0];
}

/** The `from_ts` (ms) for a range, or undefined for "all time". */
export function rangeFromTs(key: RangeKey, now: number = Date.now()): number | undefined {
  const { ms } = rangePreset(key);
  return ms == null ? undefined : now - ms;
}

/**
 * A `<input type="datetime-local">` value (local wall-clock, with seconds) for
 * an epoch-ms timestamp. The input speaks local time, so this formats in local
 * time rather than UTC.
 */
export function tsToLocalInput(ts: number): string {
  const date = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

/** Parse a `datetime-local` value (local time) back to epoch ms, or null. */
export function localInputToTs(value: string): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) ? ms : null;
}

/**
 * Cap a series to `maxPoints` for plotting, keeping the newest points and an
 * even spread of the rest. A window can now return hundreds of thousands of
 * rows; a chart cannot render them, so it is downsampled while the true total is
 * reported separately from the device's stream count.
 */
export function downsample(
  records: SensorRecord[],
  maxPoints = 2000,
): SensorRecord[] {
  if (records.length <= maxPoints) return records;
  const step = records.length / maxPoints;
  const sampled: SensorRecord[] = [];
  for (let i = 0; i < maxPoints; i++) {
    sampled.push(records[Math.floor(i * step)]);
  }
  // Always keep the most recent record so the chart ends where the data does.
  const last = records[records.length - 1];
  if (sampled[sampled.length - 1] !== last) sampled.push(last);
  return sampled;
}

/** Whether a record falls inside a range window (used for client-side trims). */
export function withinRange(
  record: SensorRecord,
  key: RangeKey,
  now: number = Date.now(),
): boolean {
  const from = rangeFromTs(key, now);
  if (from == null) return true;
  const ts = normalizeTimestamp(record.timestamp);
  return ts != null && ts >= from;
}
