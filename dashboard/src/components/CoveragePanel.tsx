import { useMemo } from "react";
import { Link } from "react-router-dom";
import { fetchStudyCoverage, studyCoverageWorkbookHref } from "../api/client";
import { SENSOR_CONFIGS } from "../config/sensors";
import type { CoverageBucket, CoverageLevel, StudyCoverage } from "../types";
import {
  deviceCoverageHref,
  useCoverageGrid,
  useCoverageView,
} from "../utils/coverageView";
import CoverageHeatmap, {
  CoverageLegend,
  type HeatmapRow,
} from "./CoverageHeatmap";
import PlatformIcon from "./PlatformIcon";
import TimezonePicker from "./TimezonePicker";

/**
 * The study coverage view: did the data arrive when it should have, and where
 * did it not.
 *
 * The drill-down is the question a researcher actually asks, one level at a
 * time. Start at the year — did data arrive in the months it should have? A thin
 * month is worth opening: within it, which days? A thin day opens again: which
 * hours? Every level is the same request at a different bucket width, so
 * clicking a column is a re-query rather than a different feature.
 *
 * The whole view lives in the URL — level, anchor, platform, sensor, timezone —
 * because a coverage finding is something a researcher sends to a colleague, and
 * a link that reopens someone else's default view is not the finding.
 */

const LEVEL_LABEL: Record<CoverageLevel, string> = {
  month: "Months of",
  day: "Days of",
  hour: "Hours of",
};

/** What the anchor names at each level, for the breadcrumb. */
function anchorLabel(
  level: CoverageLevel,
  anchor: number,
  timezone: string,
): string {
  const options: Intl.DateTimeFormatOptions =
    level === "month"
      ? { year: "numeric" }
      : level === "day"
        ? { year: "numeric", month: "long" }
        : { year: "numeric", month: "long", day: "numeric" };
  return new Intl.DateTimeFormat(undefined, { ...options, timeZone: timezone }).format(
    anchor,
  );
}

const SENSOR_LABEL = new Map(SENSOR_CONFIGS.map((s) => [s.key, s.label]));

function sensorLabel(key: string): string {
  return SENSOR_LABEL.get(key) ?? key;
}

/** The levels above the current one, so a reader can step back out. */
function trailFor(level: CoverageLevel): CoverageLevel[] {
  if (level === "hour") return ["month", "day"];
  if (level === "day") return ["month"];
  return [];
}

export default function CoveragePanel() {
  const { level, anchor, platform, sensor, timezone, update } = useCoverageView();

  const { grid, stale, failed } = useCoverageGrid<StudyCoverage>(
    `study|${level}|${anchor}|${platform}|${sensor}|${timezone}`,
    () => fetchStudyCoverage({ level, anchor, platform, sensor, tz: timezone }),
  );

  const rows: HeatmapRow[] = useMemo(() => {
    if (!grid) return [];
    return grid.rows.map((row) => ({
      key: `${row.platform}:${row.device_id}`,
      label: row.device_id,
      heading: (
        // The row heading opens that phone's own grid at the same span and
        // timezone, landing on its coverage section — the study grid says which
        // device came in short, and this is the next question a reader asks.
        <Link
          to={deviceCoverageHref(row.platform, row.device_id, {
            level,
            anchor,
            timezone,
          })}
          title={`Open ${row.device_id} — its coverage per sensor, same period`}
          className="flex items-center gap-1.5 text-ink no-underline transition-colors hover:text-teal"
        >
          <PlatformIcon platform={row.platform} className="h-4 w-4 shrink-0" />
          <span className="truncate font-mono text-[13px]">
            #{row.device_id.slice(0, 8)}
          </span>
          {/* The exports leave this device out, so the grid says so. A row that
              looked ordinary here and then went missing from an archive is the
              discrepancy worth preventing. */}
          {row.excluded ? (
            <span
              title={
                row.excluded.note
                  ? `Left out of the analysis: ${row.excluded.note}`
                  : "Left out of the analysis"
              }
              className="shrink-0 rounded border border-short/40 bg-short/10 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-[0.3px] text-short"
            >
              excl
            </span>
          ) : null}
        </Link>
      ),
      cells: row.cells,
      records: row.records,
    }));
  }, [grid, level, anchor, timezone]);

  /** Opening a column: the next level down, anchored inside that column. */
  function openColumn(bucket: CoverageBucket) {
    if (!grid?.drills_into) return;
    update({ level: grid.drills_into, at: String(bucket.from) });
  }

  const trail = trailFor(level);
  const selectableSensors = useMemo(() => {
    const available = platform
      ? SENSOR_CONFIGS.filter((s) => s.tables[platform] != null)
      : SENSOR_CONFIGS;
    return [...available].sort((a, b) => a.label.localeCompare(b.label));
  }, [platform]);

  const controlClass =
    "h-8 rounded-lg border border-wire bg-card-strong px-2 text-[12px] text-ink transition-colors hover:border-teal focus:border-teal focus:outline-none";

  return (
    <section className="mt-5 rounded-2xl border border-wire bg-card p-4 shadow-card">
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sage">
            Coverage
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[14px] text-ink">
            {trail.map((step) => (
              <button
                key={step}
                type="button"
                onClick={() => update({ level: step })}
                className="cursor-pointer rounded px-1 text-[13px] text-sage underline decoration-wire underline-offset-2 transition-colors hover:text-teal"
              >
                {anchorLabel(step, anchor, timezone)}
              </button>
            ))}
            {trail.length > 0 ? <span className="text-sage/60">/</span> : null}
            <span className="font-medium">
              {LEVEL_LABEL[level]} {anchorLabel(level, anchor, timezone)}
            </span>
          </div>
          <p className="mt-1 max-w-[46rem] text-[12px] leading-relaxed text-sage">
            {sensor
              ? `How much ${sensorLabel(sensor)} arrived in each bucket.`
              : "How many of the sensors the study asks for reported in each bucket."}{" "}
            {grid?.drills_into
              ? "Click a column heading to open it."
              : "The finest level: each column is one hour."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={sensor ?? ""}
            onChange={(event) =>
              update({ csensor: event.target.value || null })
            }
            className={controlClass}
            title="One sensor, or every required sensor at once"
          >
            <option value="">All required sensors</option>
            {selectableSensors.map((config) => (
              <option key={config.key} value={config.key}>
                {config.label}
              </option>
            ))}
          </select>

          <select
            value={platform ?? ""}
            onChange={(event) =>
              update({ cplatform: event.target.value || null })
            }
            className={controlClass}
            title="Rows and sensors differ across platforms, so all platforms means the union"
          >
            <option value="">All platforms</option>
            <option value="android">Android</option>
            <option value="ios">iPhone</option>
          </select>

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
        <div className="h-32 rounded-xl shimmer" />
      ) : (
        // The previous grid stays up while the next one loads, dimmed, so
        // stepping through days does not blank the view between each one.
        <div className={stale ? "opacity-50 transition-opacity" : undefined}>
          <CoverageHeatmap
            buckets={grid.buckets}
            rows={rows}
            maxRecords={grid.max_records}
            timezone={grid.timezone}
            rowHeader="Device"
            onColumnClick={grid.drills_into ? openColumn : undefined}
            emptyMessage={
              sensor
                ? `No phone on this platform collects ${sensorLabel(sensor)}.`
                : "No devices have enrolled yet."
            }
          />
          {/* How much the exclusions leave out. Marking rows says who is out; this
              says whether that is a rounding error or a third of the study, which
              is the difference a reader needs before trusting an export. */}
          {grid.excluded.devices > 0 ? (
            <p className="mt-3 rounded-xl border border-short/40 bg-short/10 px-3 py-2 text-[12px] text-short">
              {grid.excluded.records.toLocaleString()}{" "}
              {grid.excluded.records === 1 ? "record" : "records"} from{" "}
              {grid.excluded.devices.toLocaleString()}{" "}
              {grid.excluded.devices === 1 ? "device" : "devices"} are left out of
              the analysis and will not appear in an export. The rows below still
              show what those devices collected.
            </p>
          ) : null}

          <div className="mt-3 flex flex-col gap-2 border-t border-wire pt-2.5 sm:flex-row sm:items-center sm:justify-between">
            <CoverageLegend />
            <span className="flex items-center gap-3 text-[11px] text-sage/80">
              Buckets are whole hours, in {grid.timezone}.
              {/* The grid as it stands, so the file a researcher circulates
                  carries the colours and totals they were reading. */}
              <a
                href={studyCoverageWorkbookHref({
                  level,
                  anchor,
                  platform,
                  sensor,
                  tz: grid.timezone,
                })}
                title="Excel: this grid, with each cell's count, its colour, and totals per row and column"
                className="inline-flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-wire bg-card-strong px-2 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage no-underline transition-colors hover:border-teal hover:text-teal"
              >
                ↓ Excel
              </a>
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
