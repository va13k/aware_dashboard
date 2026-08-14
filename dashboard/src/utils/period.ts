import type { ChosenPeriod } from "../types";

/**
 * All time, said explicitly rather than left as the absence of a choice.
 *
 * Kept out of the picker itself so the dialogs can name the same value without
 * importing a component.
 */
export const ALL_TIME: ChosenPeriod = { from: null, to: null, label: "All time" };

/** A record count at the size a researcher reads rather than counts. */
export function recordsLabel(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M records`;
  if (count >= 1_000) return `${Math.round(count / 1000)}K records`;
  return `${count} record${count === 1 ? "" : "s"}`;
}

/** Identity of a count request, so a stale answer can be told from a current one. */
export function countKey(
  period: ChosenPeriod | null,
  platform: string | null,
  sensor: string | null,
  device: string | null = null,
): string {
  if (!period) return "";
  return `${period.from}:${period.to}:${platform ?? ""}:${sensor ?? ""}:${device ?? ""}`;
}

/**
 * A download size at the precision worth showing.
 *
 * Deliberately coarse: the figure behind it is an estimate that can be out by
 * half either way, so a decimal place would claim a confidence it has not got.
 */
export function sizeLabel(bytes: number): string {
  if (bytes >= 1_000_000_000) return `~${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `~${Math.round(bytes / 1_000_000)} MB`;
  if (bytes >= 1_000) return `~${Math.round(bytes / 1_000)} KB`;
  return `${bytes} B`;
}
