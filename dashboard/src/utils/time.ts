/**
 * Every timestamp the dashboard renders goes through here.
 *
 * The API returns timestamps in milliseconds, but sensor tables have historically
 * held seconds as well, so a value has to be normalised before it is read as a
 * date. That normalisation used to be repeated in three pages with three
 * different thresholds, and the relative-age labels in four.
 */

/** Below this, a value is seconds rather than milliseconds. */
const SECONDS_THRESHOLD = 1e11;

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** A timestamp in milliseconds, or null when there is nothing usable to show. */
export function normalizeTimestamp(value: unknown): number | null {
  const raw =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : NaN;

  if (!Number.isFinite(raw) || raw <= 0) return null;
  return raw < SECONDS_THRESHOLD ? raw * 1000 : raw;
}

/**
 * How long ago something happened: "just now", "8m ago", "3h ago", "2d ago".
 *
 * `never` for a missing timestamp - a phone that has never uploaded is a normal
 * state in a study, not an error.
 */
export function relativeAge(value: unknown, now: number = Date.now()): string {
  const timestamp = normalizeTimestamp(value);
  if (timestamp == null) return "never";

  const seconds = Math.floor((now - timestamp) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 10) return "just now";
  if (seconds < MINUTE) return `${seconds}s ago`;
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m ago`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h ago`;
  return `${Math.floor(seconds / DAY)}d ago`;
}

/** Date and time, for tooltips and single-value headlines. */
export function absoluteTime(value: unknown): string {
  const timestamp = normalizeTimestamp(value);
  if (timestamp == null) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

/** Date and time down to the second, for logs where the exact moment matters. */
export function absoluteTimeWithSeconds(value: unknown): string {
  const timestamp = normalizeTimestamp(value);
  if (timestamp == null) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(timestamp));
}

/** Date only, for spans where the time of day carries no meaning. */
export function absoluteDate(value: unknown): string {
  const timestamp = normalizeTimestamp(value);
  if (timestamp == null) return "—";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(timestamp));
}

/** An ISO string the API generated, rather than a device timestamp. */
export function isoDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/** The most recent of several timestamps, in milliseconds, or null. */
export function latestTimestamp(values: readonly unknown[]): number | null {
  let latest: number | null = null;
  for (const value of values) {
    const timestamp = normalizeTimestamp(value);
    if (timestamp != null && (latest == null || timestamp > latest)) {
      latest = timestamp;
    }
  }
  return latest;
}

/** A gap between two events: "920ms", "53.2s", "4m 13s". */
export function durationLabel(milliseconds: unknown): string {
  const value = typeof milliseconds === "number" ? milliseconds : NaN;
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 1000) return `${Math.round(value)}ms`;

  const seconds = value / 1000;
  if (seconds < MINUTE) return `${seconds.toFixed(1)}s`;

  const minutes = Math.floor(seconds / MINUTE);
  const remainder = Math.round(seconds - minutes * MINUTE);
  if (minutes < MINUTE) return `${minutes}m ${remainder}s`;

  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes - hours * 60}m`;
}

/**
 * The timezone the browser is in, for cutting coverage buckets into the days a
 * participant actually lived. UTC when the browser will not say.
 */
export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
