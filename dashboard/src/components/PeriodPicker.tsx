import { useEffect, useMemo, useState } from "react";
import { fetchCoverageCounts, fetchCoverageWindows } from "../api/client";
import type { ChosenPeriod, CoverageWindow, CoverageWindows } from "../types";
import { absoluteTime } from "../utils/time";
import { localInputToTs, tsToLocalInput } from "../utils/timeRange";
import { ALL_TIME, countKey, recordsLabel as records, sizeLabel } from "../utils/period";

const ANCHORS: { key: "data" | "now"; label: string; hint: string }[] = [
  { key: "data", label: "Newest data", hint: "counted back from the last row stored" },
  { key: "now", label: "Right now", hint: "counted back from the current time" },
];

function periodOf(window: CoverageWindow): ChosenPeriod {
  return {
    from: window.from,
    to: window.to,
    label: `${window.label} to ${window.anchor === "data" ? "newest data" : "now"}`,
  };
}

function sameWindow(a: ChosenPeriod | null, b: ChosenPeriod | null): boolean {
  return a?.from === b?.from && a?.to === b?.to;
}

/**
 * Picking the period an export covers.
 *
 * One question — which period — because scope is decided by the button that
 * opened the dialog rather than by a control inside it.
 *
 * Every choice resolves to a concrete pair of instants and shows them. A
 * relative period is what a researcher thinks in, but "the last week" names a
 * different week each day it is clicked, and an export nobody can reproduce
 * later is an export nobody can cite.
 *
 * The count beside the selection is scoped to whatever the dialog is exporting,
 * so it answers the question actually being asked — how much am I about to
 * download — rather than how much the study holds.
 */
export default function PeriodPicker({
  value,
  onChange,
  onCount,
  platform = null,
  sensor = null,
}: {
  value: ChosenPeriod | null;
  onChange: (period: ChosenPeriod) => void;
  /** How many records the current choice covers; null while it is unknown. */
  onCount?: (total: number | null) => void;
  platform?: "android" | "ios" | null;
  sensor?: string | null;
}) {
  const [offer, setOffer] = useState<CoverageWindows | null>(null);
  const [failed, setFailed] = useState(false);
  const [custom, setCustom] = useState(false);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  // Held with the request it answered, so a count left over from the previous
  // selection is never shown against the current one.
  const [counted, setCounted] = useState<{
    key: string;
    total: number | null;
    bytes: number;
  } | null>(null);

  useEffect(() => {
    fetchCoverageWindows()
      .then(setOffer)
      .catch(() => setFailed(true));
  }, []);

  // The count follows the selection and the scope, so a sensor dialog reports
  // that sensor rather than the study.
  const key = countKey(value, platform, sensor);
  useEffect(() => {
    if (!value) return;
    let cancelled = false;
    fetchCoverageCounts({ from: value.from, to: value.to, platform, sensor })
      .then((body) => {
        if (cancelled) return;
        setCounted({ key, total: body.total, bytes: body.estimated_bytes ?? 0 });
        onCount?.(body.total);
      })
      .catch(() => {
        if (cancelled) return;
        setCounted({ key, total: null, bytes: 0 });
        // Unknown, not empty: a count that failed to load must not be the
        // reason a researcher cannot download something that is there.
        onCount?.(null);
      });
    return () => {
      cancelled = true;
    };
    // `onCount` deliberately absent: a caller passing an inline arrow would
    // otherwise refetch on every render of its parent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, value, platform, sensor]);

  const counting = Boolean(value) && counted?.key !== key;
  const count = counted?.key === key ? counted.total : null;
  const bytes = counted?.key === key ? counted.bytes : 0;

  const byAnchor = useMemo(() => {
    const grouped: Record<string, CoverageWindow[]> = { data: [], now: [] };
    for (const window of offer?.windows ?? []) grouped[window.anchor]?.push(window);
    return grouped;
  }, [offer]);

  const chooseCustom = (fromValue: string, toValue: string) => {
    const from = localInputToTs(fromValue);
    const to = localInputToTs(toValue);
    if (from == null || to == null) return;
    const [start, end] = from <= to ? [from, to] : [to, from];
    onChange({ from: start, to: end, label: "Custom range" });
  };

  const openCustom = () => {
    setCustom(true);
    const end = offer?.newest ?? offer?.now ?? Date.now();
    const start = end - 24 * 60 * 60 * 1000;
    const fromValue = customFrom || tsToLocalInput(start);
    const toValue = customTo || tsToLocalInput(end);
    setCustomFrom(fromValue);
    setCustomTo(toValue);
    chooseCustom(fromValue, toValue);
  };

  const preset =
    "rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors";
  const chosen = "border-teal bg-teal-soft text-teal";
  const idle = "border-wire bg-card-strong text-sage hover:border-teal hover:text-teal";
  const off = "cursor-not-allowed border-wire bg-card-strong text-sage/30";

  if (failed) {
    return (
      <p className="text-[12px] text-red-600">
        Could not load the periods on offer. The export can still run over all time.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {ANCHORS.map((anchor) => (
        <div key={anchor.key}>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-sage">
            {anchor.label}{" "}
            <span className="font-normal normal-case tracking-normal">
              — {anchor.hint}
            </span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {(byAnchor[anchor.key] ?? []).map((window) => {
              const period = periodOf(window);
              const active = !custom && sameWindow(value, period);
              return (
                <button
                  key={window.key}
                  type="button"
                  disabled={!window.available}
                  title={
                    window.available
                      ? `${records(window.records)} across the study`
                      : "Nothing was recorded in this period"
                  }
                  onClick={() => {
                    setCustom(false);
                    onChange(period);
                  }}
                  className={`${preset} ${
                    !window.available ? off : active ? chosen : idle
                  }`}
                >
                  {window.label}
                </button>
              );
            })}
            {!offer && (
              <span className="text-[11px] text-sage">Loading periods…</span>
            )}
          </div>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => {
            setCustom(false);
            onChange(ALL_TIME);
          }}
          className={`${preset} ${
            !custom && sameWindow(value, ALL_TIME) ? chosen : idle
          }`}
        >
          All time
        </button>
        <button
          type="button"
          onClick={openCustom}
          className={`${preset} ${custom ? chosen : idle}`}
        >
          Custom range
        </button>
      </div>

      {custom && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-wire bg-card-strong p-2.5">
          <label className="text-[10px] font-semibold uppercase tracking-[0.5px] text-sage">
            From
            <input
              type="datetime-local"
              step="1"
              value={customFrom}
              onChange={(event) => {
                setCustomFrom(event.target.value);
                chooseCustom(event.target.value, customTo);
              }}
              className="ml-1.5 rounded-lg border border-wire bg-card px-2 py-1 text-[11px] font-normal normal-case tracking-normal text-ink"
            />
          </label>
          <label className="text-[10px] font-semibold uppercase tracking-[0.5px] text-sage">
            To
            <input
              type="datetime-local"
              step="1"
              value={customTo}
              onChange={(event) => {
                setCustomTo(event.target.value);
                chooseCustom(customFrom, event.target.value);
              }}
              className="ml-1.5 rounded-lg border border-wire bg-card px-2 py-1 text-[11px] font-normal normal-case tracking-normal text-ink"
            />
          </label>
        </div>
      )}

      {/* The instants the choice resolves to, always shown. This is what makes
          the export reproducible from its own name months later. */}
      <div className="rounded-xl border border-wire bg-card-strong px-3 py-2">
        {!value ? (
          <p className="text-[11px] text-sage">Pick a period to export.</p>
        ) : (
          <>
            <p className="text-[11px] font-semibold text-ink">{value.label}</p>
            <p className="mt-0.5 text-[11px] text-sage">
              {value.from == null && value.to == null
                ? "Everything the study holds"
                : `${value.from == null ? "the beginning" : absoluteTime(value.from)} — ${
                    value.to == null ? "now" : absoluteTime(value.to)
                  }`}
            </p>
            <p className="mt-1 text-[11px] text-sage">
              {counting
                ? "Counting…"
                : count == null
                  ? "Count unavailable"
                  : count === 0
                    ? "Nothing to export in this period"
                    : records(count)}
              {!counting && count && bytes ? (
                <span className="font-semibold text-ink"> · {sizeLabel(bytes)}</span>
              ) : null}
            </p>
            {!counting && count ? (
              <p className="mt-0.5 text-[10px] text-sage/60">
                Counted to the hour. The size is a rough estimate — the file is
                often smaller.
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
