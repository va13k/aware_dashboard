import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { CoverageLevel } from "../types";
import { browserTimezone } from "./time";

/**
 * The state a coverage grid is read at, held in the URL.
 *
 * In the URL rather than in the component because a coverage finding is
 * something a researcher sends to a colleague — "look at the 9th" — and a link
 * that reopens the recipient's default view is not the finding. Level, anchor,
 * platform, sensor and timezone all travel.
 *
 * Both grids share this so the study view and the device view cannot drift into
 * reading the same query parameters differently.
 */

export interface CoverageViewState {
  level: CoverageLevel;
  anchor: number;
  platform: "android" | "ios" | null;
  sensor: string | null;
  timezone: string;
  /** Writes only the keys given, so one control cannot clear another's. */
  update: (changes: Record<string, string | null>) => void;
}

function isLevel(value: string | null): value is CoverageLevel {
  return value === "month" || value === "day" || value === "hour";
}

export function useCoverageView(): CoverageViewState {
  const [params, setParams] = useSearchParams();

  // Read once, so a grid opened with no anchor does not shift under the reader
  // as the clock moves and every re-render agrees on which day is being shown.
  const [openedAt] = useState(() => Date.now());

  const level = isLevel(params.get("level")) ? (params.get("level") as CoverageLevel) : "day";
  const anchorParam = Number(params.get("at"));
  const anchor = Number.isFinite(anchorParam) && anchorParam > 0 ? anchorParam : openedAt;
  const platformParam = params.get("cplatform");
  const platform =
    platformParam === "android" || platformParam === "ios" ? platformParam : null;

  const [localZone] = useState(browserTimezone);

  const update = useCallback(
    (changes: Record<string, string | null>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value == null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return {
    level,
    anchor,
    platform,
    sensor: params.get("csensor"),
    timezone: params.get("tz") ?? localZone,
    update,
  };
}

/**
 * One grid, fetched for the current view.
 *
 * `stale` is derived by comparing what arrived against what is being asked for,
 * rather than by flipping a loading flag as the request goes out. That keeps the
 * effect free of synchronous state updates, and it keeps the previous grid on
 * screen while the next one loads — which matters when a reader is stepping
 * through days and a blank frame between each one reads as data disappearing.
 */
export function useCoverageGrid<T>(
  key: string,
  load: () => Promise<T>,
): { grid: T | null; stale: boolean; failed: boolean } {
  const [result, setResult] = useState<{
    key: string;
    grid: T | null;
    failed: boolean;
  } | null>(null);

  // `load` is rebuilt every render by callers; the key is what identifies the
  // request, so the effect follows that rather than the function identity.
  const loader = useMemo(() => load, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    loader()
      .then((grid) => {
        if (live) setResult({ key, grid, failed: false });
      })
      .catch(() => {
        if (live) setResult({ key, grid: null, failed: true });
      });
    return () => {
      live = false;
    };
  }, [key, loader]);

  return {
    grid: result?.grid ?? null,
    stale: result?.key !== key,
    failed: result?.key === key && result.failed,
  };
}
