import { useEffect, useMemo, useRef } from "react";
import { useLocation } from "react-router-dom";
import { fetchDeviceCoverage } from "../api/client";
import { SENSOR_CONFIGS } from "../config/sensors";
import type { CoverageBucket, CoverageLevel, DeviceCoverage } from "../types";
import {
  COVERAGE_ANCHOR,
  useCoverageGrid,
  useCoverageView,
} from "../utils/coverageView";
import CoverageHeatmap, {
  CoverageLegend,
  type HeatmapRow,
} from "./CoverageHeatmap";
import TimezonePicker from "./TimezonePicker";

/**
 * One phone's coverage: a sensor per row, the same buckets as the study grid.
 *
 * The study view cannot answer this — there a row is a whole device across every
 * sensor at once, so a phone that stopped collecting one thing looks like a phone
 * that is fine. Here the question is "is this phone collecting everything it
 * should", and a required sensor with an empty row is the answer.
 *
 * Required sensors come first, because a sensor the study asked for and did not
 * get is the finding; anything else the phone is uploading follows, which is
 * worth seeing when a sensor was switched off in the config and kept going.
 */

const LEVEL_LABEL: Record<CoverageLevel, string> = {
  month: "Months of",
  day: "Days of",
  hour: "Hours of",
};

const SENSOR_LABEL = new Map(SENSOR_CONFIGS.map((s) => [s.key, s.label]));

const NUMBER = new Intl.NumberFormat();

/** The rate a row is judged against, said in the unit a reader thinks in. */
function rateNote(perHour: number | null, basis: string | null): string {
  if (basis === "event") return "on event";
  if (perHour == null) return "";
  if (perHour >= 1) return `≈${NUMBER.format(Math.round(perHour))}/h`;
  return `≈${NUMBER.format(Math.round(perHour * 24))}/day`;
}

export default function DeviceCoveragePanel({
  platform,
  deviceId,
}: {
  platform: "android" | "ios";
  deviceId: string;
}) {
  const { level, anchor, timezone, update } = useCoverageView();

  const { grid, stale, failed } = useCoverageGrid<DeviceCoverage>(
    `device|${platform}|${deviceId}|${level}|${anchor}|${timezone}`,
    () => fetchDeviceCoverage(platform, deviceId, { level, anchor, tz: timezone }),
  );

  const section = useRef<HTMLElement>(null);
  const { hash } = useLocation();
  const arrived = useRef(false);

  // A link from the study grid names this section in its hash. Scrolled once the
  // first grid has rendered, since the page's height settles with it — and only
  // once, so a level change later leaves the reader where they are.
  useEffect(() => {
    if (arrived.current || grid == null) return;
    if (hash !== `#${COVERAGE_ANCHOR}`) return;
    arrived.current = true;
    section.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [grid, hash]);

  const rows: HeatmapRow[] = useMemo(() => {
    if (!grid) return [];
    const ordered = [...grid.rows].sort((a, b) => {
      if (a.required !== b.required) return a.required ? -1 : 1;
      return (SENSOR_LABEL.get(a.sensor) ?? a.sensor).localeCompare(
        SENSOR_LABEL.get(b.sensor) ?? b.sensor,
      );
    });
    return ordered.map((row) => ({
      key: row.sensor,
      label: SENSOR_LABEL.get(row.sensor) ?? row.sensor,
      heading: (
        <span className="flex items-center gap-1.5">
          <span className="truncate">
            {SENSOR_LABEL.get(row.sensor) ?? row.sensor}
          </span>
          {!row.required ? (
            <span
              title="Uploading, but the study config does not ask for it"
              className="shrink-0 rounded border border-wire px-1 text-[10px] uppercase tracking-[0.3px] text-sage"
            >
              extra
            </span>
          ) : null}
        </span>
      ),
      cells: row.cells,
      records: row.records,
      note: rateNote(row.expected_per_hour, row.basis),
    }));
  }, [grid]);

  function openColumn(bucket: CoverageBucket) {
    if (!grid?.drills_into) return;
    update({ level: grid.drills_into, at: String(bucket.from) });
  }

  const anchorText = new Intl.DateTimeFormat(undefined, {
    ...(level === "month"
      ? { year: "numeric" }
      : level === "day"
        ? { year: "numeric", month: "long" }
        : { year: "numeric", month: "long", day: "numeric" }),
    timeZone: timezone,
  }).format(anchor);

  const controlClass =
    "h-8 rounded-lg border border-wire bg-card-strong px-2 text-[12px] text-ink transition-colors hover:border-teal focus:border-teal focus:outline-none";

  return (
    <section
      id={COVERAGE_ANCHOR}
      ref={section}
      // Scrolled to from a study-grid row, so the heading clears the sticky header.
      className="mt-5 scroll-mt-20 rounded-2xl border border-wire bg-card p-4 shadow-card"
    >
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[13px] font-semibold uppercase tracking-[0.6px] text-sage">
            Coverage
          </div>
          <div className="mt-1 text-[16px] font-medium text-ink">
            {LEVEL_LABEL[level]} {anchorText}
          </div>
          <p className="mt-1 max-w-[46rem] text-[14px] leading-relaxed text-sage">
            What this phone sent, per sensor.{" "}
            {grid?.drills_into
              ? "Click a column heading to open it."
              : "The finest level: each column is one hour."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <TimezonePicker
            value={timezone}
            onChange={(zone) => update({ tz: zone })}
            className={controlClass}
          />
          <select
            value={level}
            onChange={(event) =>
              update({ level: event.target.value as CoverageLevel })
            }
            className={controlClass}
            title="The width of one column"
          >
            <option value="month">Months</option>
            <option value="day">Days</option>
            <option value="hour">Hours</option>
          </select>
        </div>
      </div>

      {failed ? (
        <div className="rounded-xl border border-wire bg-card p-6 text-center text-[14px] text-sage">
          The coverage grid could not be loaded.
        </div>
      ) : !grid ? (
        <div className="h-40 rounded-xl shimmer" />
      ) : (
        <div className={stale ? "opacity-50 transition-opacity" : undefined}>
          <CoverageHeatmap
            buckets={grid.buckets}
            rows={rows}
            maxRecords={grid.max_records}
            timezone={grid.timezone}
            rowHeader="Sensor"
            onColumnClick={grid.drills_into ? openColumn : undefined}
            emptyMessage="The study config asks this phone for nothing, and it has sent nothing."
          />
          <div className="mt-3 flex flex-col gap-2 border-t border-wire pt-2.5 sm:flex-row sm:items-center sm:justify-between">
            <CoverageLegend />
            <span className="text-[11px] text-sage/80">
              Buckets are whole hours, in {grid.timezone}.
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
