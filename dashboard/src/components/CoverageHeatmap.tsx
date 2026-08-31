import { useMemo, useState, type ReactNode } from "react";
import type { CoverageBucket, CoverageCell } from "../types";
import {
  AGGREGATE_BAND_LEGEND,
  BAND_LEGEND,
  bandOf,
  cellFill,
} from "../utils/coverageScale";

/**
 * The coverage grid: one row per device or per sensor, one column per bucket.
 *
 * Colour reads a bucket against what the study config asked for, so a sensor that
 * came in short is visible without reading a count — the bands and what each one
 * claims live in `utils/coverageScale.ts`.
 *
 * The count itself, and the expectation it was compared with, sit in the cell's
 * detail panel. A band says which side of the configured rate a bucket fell on;
 * the two numbers say by how much, and for a sensor whose configured and
 * delivered rates differ by orders of magnitude that is what a reader needs
 * before acting on the colour.
 *
 * That detail is drawn rather than left to the browser's own `title` tooltip,
 * whose delay is set by the operating system and runs to over a second. A grid is
 * read by sweeping across it, so the detail appears the moment the pointer lands
 * on a cell. A tap opens the same panel, which is how it is reached where there is
 * no pointer to hover with.
 */

/**
 * Column widths, in pixels. Every bucket is this wide exactly, at every level, so
 * a cell is the same square whether the grid is showing twelve months or
 * thirty-one days. Sharing the leftover width between the buckets instead would
 * land them on fractions of a pixel that differ from each other by a tenth.
 *
 * The width is set by the footer rather than by the cells: a shortened total runs
 * to about 24px, so the column carries that plus the space that keeps `930K` and
 * `751K` reading as two figures instead of one.
 */
const BUCKET_COLUMN = 32;
/** Wide enough for a row's total and the rate it is judged against beside it. */
const TOTAL_COLUMN = 156;
/** The row heading takes what is left over, down to this. */
const MIN_LABEL_COLUMN = 208;

const NUMBER = new Intl.NumberFormat();

/**
 * A total shortened to fit a bucket column: `930K`, `2.9M`, `51K`.
 *
 * Written out rather than taken from `Intl` compact notation, for two reasons the
 * column width makes matter. Two significant figures keeps every output to four
 * characters and about 24px wide, where compact notation's one decimal place
 * produces `194.1K` at 33px. And the suffix is the same in every locale, where
 * compact notation renders a million as a lowercase `1m` in some of them —
 * leaving the gap between two totals to vary with the reader's language.
 */
function shortCount(value: number): string {
  if (value <= 0) return "";
  for (const [limit, suffix] of [
    [1_000_000_000, "B"],
    [1_000_000, "M"],
    [1_000, "K"],
  ] as const) {
    if (value >= limit) {
      const scaled = value / limit;
      const figure =
        scaled < 10 ? scaled.toFixed(1).replace(/\.0$/, "") : Math.round(scaled);
      return `${figure}${suffix}`;
    }
  }
  return String(Math.round(value));
}

function recordCount(count: number): string {
  return `${NUMBER.format(count)} record${count === 1 ? "" : "s"}`;
}

function bucketRange(bucket: CoverageBucket, timezone: string): string {
  const format = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  });
  return `${format.format(bucket.from)} — ${format.format(bucket.to)}`;
}

const BAND_SUMMARY: Record<string, string> = {
  blank: "Nothing expected — outside this device's enrolment.",
  none: "Expected, and nothing arrived.",
  short: "Well under the rate the study config asks for.",
  moderate: "Approaching the rate the study config asks for.",
  expected: "At the rate the study config asks for.",
  over: "Far above the rate the study config asks for.",
  unjudged: "Arrived. No configured rate to compare it with.",
};

/**
 * `unjudged` where a rate does exist but the phone filters what reaches the table.
 * The band's own wording denies a rate the researcher can see in the config, and
 * would send them looking for the missing setting instead of at the filter.
 */
const GATED_SUMMARY =
  "Arrived. The phone filters this sensor, so the amount is not judged.";

/**
 * The same bands on the all-sensors grid, where they count sensors rather than rows.
 *
 * `aggregate_band` decides the colour from the share of required sensors that
 * reported anything, so the rate wording above describes a different
 * measurement. A cell reading "well under the configured rate" when it means
 * "six of eighteen sensors reported" sends a reader looking at volume for a
 * problem that is one of breadth.
 */
const AGGREGATE_BAND_SUMMARY: Record<string, string> = {
  blank: "Nothing expected — outside this device's enrolment.",
  none: "Expected, and no required sensor reported.",
  short: "Under half the required sensors reported.",
  moderate: "Most of the required sensors reported, but not all.",
  expected: "Every required sensor reported.",
  unjudged: "Arrived outside the enrolment — the study asked for none.",
};

/** Whether a cell is judged by how many sensors reported rather than by a rate. */
function isAggregate(cell: CoverageCell): boolean {
  return cell.required != null;
}

/** What a cell's detail says, in the order a reader needs it. */
function cellDetail(
  cell: CoverageCell,
  bucket: CoverageBucket,
  rowLabel: string,
  timezone: string,
): string[] {
  const band = bandOf(cell);
  const aggregate = isAggregate(cell);
  const lines = [
    `${rowLabel} · ${bucketRange(bucket, timezone)}`,
    // The rate wording is the fallback: `aggregate_band` produces no `over`, and
    // a band this table has yet to learn still gets a sentence.
    (aggregate ? AGGREGATE_BAND_SUMMARY[band] : null) ??
      (cell.ceiling && band === "unjudged" ? GATED_SUMMARY : BAND_SUMMARY[band]),
  ];

  if (band === "blank") return lines;

  if (aggregate) {
    lines.push(
      `${cell.reporting} of ${cell.required} required sensors reported`,
      recordCount(cell.records ?? 0),
      // The colour is a count of streams, so the row total says nothing about
      // it: a phone sending one sensor hard reads red beside a large number.
      "The colour counts sensors, not records. Pick a sensor above to judge amounts.",
    );
    return lines;
  }

  lines.push(recordCount(cell.records));

  if (cell.expected != null) {
    const verb = cell.floor ? "at least" : cell.ceiling ? "at most" : "about";
    lines.push(`Config implies ${verb} ${NUMBER.format(Math.round(cell.expected))}`);
    if (cell.floor) {
      lines.push("That figure bounds the scans, not the rows each one yields.");
    }
  } else if (cell.basis === "event") {
    lines.push("Event sensor — the phone writes when something happens.");
  } else if (cell.basis === "unconfigured") {
    lines.push("The study config carries no rate for this sensor.");
  }

  if (cell.hours > 0 && cell.hours < 1) {
    lines.push(`Enrolled for ${Math.round(cell.hours * 60)} min of this bucket.`);
  } else if (cell.hours === 0 && cell.records > 0) {
    // The colour says the count is unjudged; this says why it could not be judged.
    lines.push("Arrived outside the enrolment window — the study asked for none.");
  }

  return lines;
}

interface Detail {
  /** Identifies the cell it belongs to, so tapping the same one closes it. */
  key: string;
  lines: string[];
  /** Viewport coordinates of the cell it points at. */
  centre: number;
  above: number;
  below: number;
}

/** Half the panel's widest possible width, for keeping it inside the viewport. */
const DETAIL_REACH = 180;
/** Room a panel needs above a cell before it is drawn below it instead. */
const DETAIL_HEIGHT = 150;

function detailFor(
  element: HTMLElement,
  key: string,
  lines: string[],
): Detail {
  const rect = element.getBoundingClientRect();
  return {
    key,
    lines,
    // Clamped here rather than while rendering, so the panel stays on screen at
    // the edges of the grid without the render reading the window.
    centre: Math.min(
      Math.max(rect.left + rect.width / 2, DETAIL_REACH),
      window.innerWidth - DETAIL_REACH,
    ),
    above: rect.top,
    below: rect.bottom,
  };
}

/** The cell detail, drawn beside the cell it describes. */
function CellDetail({ detail }: { detail: Detail }) {
  const drawBelow = detail.above < DETAIL_HEIGHT;
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 w-max max-w-[22rem] rounded-lg bg-ink/95 px-3 py-2 text-[12px] leading-snug text-card-strong shadow-card"
      style={{
        left: detail.centre,
        top: drawBelow ? detail.below + 8 : detail.above - 8,
        transform: drawBelow
          ? "translateX(-50%)"
          : "translate(-50%, -100%)",
      }}
    >
      {detail.lines.map((line, index) => (
        <div key={line} className={index === 0 ? "font-semibold" : undefined}>
          {line}
        </div>
      ))}
    </div>
  );
}

export interface HeatmapRow {
  key: string;
  label: string;
  /** Rendered in place of `label` when the row heading carries more than text. */
  heading?: ReactNode;
  cells: CoverageCell[];
  records: number;
  /** Shown after the row's total, e.g. the rate it is judged against. */
  note?: string;
}

export default function CoverageHeatmap({
  buckets,
  rows,
  maxRecords,
  timezone,
  rowHeader,
  onColumnClick,
  emptyMessage = "Nothing to draw for this period.",
}: {
  buckets: CoverageBucket[];
  rows: HeatmapRow[];
  maxRecords: number;
  timezone: string;
  /** The column heading above the row labels. */
  rowHeader: string;
  /** Given when a column can be opened at the next level down. */
  onColumnClick?: (bucket: CoverageBucket) => void;
  emptyMessage?: string;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);

  // What every row put into each bucket, and into the grid as a whole. Read from
  // the cells on screen, so the footer and the columns above it always agree.
  const bucketTotals = useMemo(
    () =>
      buckets.map((_, index) =>
        rows.reduce((sum, row) => sum + (row.cells[index]?.records ?? 0), 0),
      ),
    [buckets, rows],
  );
  const gridTotal = useMemo(
    () => bucketTotals.reduce((sum, value) => sum + value, 0),
    [bucketTotals],
  );

  if (rows.length === 0 || buckets.length === 0) {
    return (
      <div className="rounded-xl border border-wire bg-card p-6 text-center text-[14px] text-sage">
        {emptyMessage}
      </div>
    );
  }

  const drillable = onColumnClick != null;
  const minWidth =
    MIN_LABEL_COLUMN + TOTAL_COLUMN + buckets.length * BUCKET_COLUMN;

  /** Opens a cell's detail. Tapping the one already open closes it again. */
  function show(element: HTMLElement, key: string, lines: string[]) {
    setDetail((current) =>
      current?.key === key ? null : detailFor(element, key, lines),
    );
  }

  return (
    <div className="overflow-x-auto" onMouseLeave={() => setDetail(null)}>
      {/* `table-fixed` with a colgroup is what makes every bucket the same size:
          the default algorithm widths a column to its content, so a column headed
          "1" comes out narrower than one headed "31" and the squares stop being
          squares. Fixed layout takes the widths from the columns instead. The
          buckets are pinned to an exact width and the row heading is left to
          absorb whatever the panel has spare, which is the column that can use
          it — a long sensor name gets more room rather than being truncated. */}
      <table
        className="w-full table-fixed border-separate border-spacing-0 text-[14px]"
        style={{ minWidth }}
      >
        <colgroup>
          <col />
          {buckets.map((bucket) => (
            <col key={bucket.key} style={{ width: BUCKET_COLUMN }} />
          ))}
          <col style={{ width: TOTAL_COLUMN }} />
        </colgroup>
        <thead>
          <tr>
            <th className="sticky left-0 z-[1] bg-card px-2 py-1 text-left text-[12px] font-semibold uppercase tracking-[0.4px] text-sage">
              {rowHeader}
            </th>
            {buckets.map((bucket) => (
              <th key={bucket.key} className="px-0 pb-1 align-bottom">
                {drillable ? (
                  <button
                    type="button"
                    onClick={() => onColumnClick?.(bucket)}
                    title={`Open ${bucketRange(bucket, timezone)}`}
                    className="w-full cursor-pointer truncate rounded text-center text-[12px] font-medium text-sage transition-colors hover:text-teal"
                  >
                    {bucket.label}
                  </button>
                ) : (
                  <span className="block truncate text-center text-[12px] font-medium text-sage">
                    {bucket.label}
                  </span>
                )}
              </th>
            ))}
            <th className="sticky right-0 z-[1] bg-card px-2 pb-1 text-right text-[12px] font-semibold uppercase tracking-[0.4px] text-sage">
              Records
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="group">
              <th
                scope="row"
                className="sticky left-0 z-[1] truncate bg-card px-2 py-0.5 text-left font-medium text-ink group-hover:bg-teal-soft/40"
                title={row.label}
              >
                {row.heading ?? row.label}
              </th>
              {row.cells.map((cell, index) => {
                const bucket = buckets[index];
                if (!bucket) return null;
                const key = `${row.key}|${bucket.key}`;
                const lines = cellDetail(cell, bucket, row.label, timezone);
                return (
                  <td key={bucket.key} className="p-[2px]">
                    <div
                      aria-label={lines.join(". ")}
                      onMouseEnter={(event) =>
                        setDetail(detailFor(event.currentTarget, key, lines))
                      }
                      onClick={(event) => show(event.currentTarget, key, lines)}
                      className={`h-5 w-full rounded-[2px] ${cellFill(
                        cell,
                        maxRecords,
                      )}`}
                    />
                  </td>
                );
              })}
              <td className="sticky right-0 z-[1] truncate bg-card px-2 py-0.5 text-right tabular-nums text-sage group-hover:bg-teal-soft/40">
                {NUMBER.format(row.records)}
                {row.note ? (
                  <span className="ml-1.5 text-[12px] text-sage/70">{row.note}</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {/* Down each column: everything every row put into that bucket. It
              answers the question the rows cannot — whether a thin-looking period
              is one quiet phone or the whole study going quiet at once. Shortened
              to fit the column, with the exact figure in the cell detail. */}
          <tr>
            <th
              scope="row"
              className="sticky left-0 z-[1] bg-card px-2 pt-1.5 text-left text-[12px] font-semibold uppercase tracking-[0.4px] text-sage"
            >
              Total
            </th>
            {bucketTotals.map((total, index) => {
              const bucket = buckets[index];
              if (!bucket) return null;
              const key = `total|${bucket.key}`;
              const lines = [
                `Total · ${bucketRange(bucket, timezone)}`,
                recordCount(total),
                `Across ${rows.length} ${rowHeader.toLowerCase()}${
                  rows.length === 1 ? "" : "s"
                }`,
              ];
              return (
                <td
                  key={bucket.key}
                  onMouseEnter={(event) =>
                    setDetail(detailFor(event.currentTarget, key, lines))
                  }
                  onClick={(event) => show(event.currentTarget, key, lines)}
                  className="overflow-hidden border-t border-wire px-[2px] pt-1 text-center text-[10px] tabular-nums text-sage"
                >
                  {shortCount(total)}
                </td>
              );
            })}
            <td className="sticky right-0 z-[1] border-t border-wire bg-card px-2 pt-1 text-right text-[12px] font-semibold tabular-nums text-ink">
              {NUMBER.format(gridTotal)}
            </td>
          </tr>
        </tfoot>
      </table>
      {detail ? <CellDetail detail={detail} /> : null}
    </div>
  );
}

/**
 * What each colour claims, beside the grid.
 *
 * `aggregate` picks the key for the all-sensors grid, whose colours grade the
 * share of required sensors that reported rather than one sensor's rate.
 */
export function CoverageLegend({ aggregate = false }: { aggregate?: boolean }) {
  const entries = aggregate ? AGGREGATE_BAND_LEGEND : BAND_LEGEND;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-sage">
      {entries.map((entry) => (
        <span key={entry.band} className="flex items-center gap-1.5">
          <span className={`h-3.5 w-3.5 shrink-0 rounded-[2px] ${entry.fill}`} />
          {entry.label}
        </span>
      ))}
    </div>
  );
}
