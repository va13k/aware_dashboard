import type { ReactNode } from "react";
import type { CoverageBucket, CoverageCell } from "../types";
import { BAND_LEGEND, bandOf, cellFill } from "../utils/coverageScale";

/**
 * The coverage grid: one row per device or per sensor, one column per bucket.
 *
 * Colour reads a bucket against what the study config asked for, so a sensor that
 * came in short is visible without reading a count — the bands and what each one
 * claims live in `utils/coverageScale.ts`.
 *
 * The count itself, and the expectation it was compared with, sit in the cell's
 * hover detail. A band says which side of the configured rate a bucket fell on;
 * the two numbers say by how much, and for a sensor whose configured and
 * delivered rates differ by orders of magnitude that is what a reader needs
 * before acting on the colour.
 */

/**
 * Column widths, in pixels. Every bucket is this wide exactly, at every level, so
 * a cell is the same square whether the grid is showing twelve months or
 * thirty-one days. Sharing the leftover width between the buckets instead would
 * land them on fractions of a pixel that differ from each other by a tenth.
 */
const BUCKET_COLUMN = 26;
const TOTAL_COLUMN = 132;
/** The row heading takes what is left over, down to this. */
const MIN_LABEL_COLUMN = 208;

const NUMBER = new Intl.NumberFormat();

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

/** What hovering a cell says, in the order a reader needs it. */
function cellTitle(
  cell: CoverageCell,
  bucket: CoverageBucket,
  rowLabel: string,
  timezone: string,
): string {
  const band = bandOf(cell);
  const lines = [
    `${rowLabel} · ${bucketRange(bucket, timezone)}`,
    BAND_SUMMARY[band],
  ];

  if (band === "blank") return lines.join("\n");

  if (cell.required != null) {
    lines.push(
      `${cell.reporting} of ${cell.required} required sensors reported`,
      recordCount(cell.records ?? 0),
    );
    return lines.join("\n");
  }

  lines.push(recordCount(cell.records));

  if (cell.expected != null) {
    const verb = cell.floor ? "at least" : "about";
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
  }

  return lines.join("\n");
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

  return (
    <div className="overflow-x-auto">
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
            <th className="sticky left-0 z-10 bg-card px-2 py-1 text-left text-[12px] font-semibold uppercase tracking-[0.4px] text-sage">
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
            <th className="px-2 pb-1 text-right text-[12px] font-semibold uppercase tracking-[0.4px] text-sage">
              Records
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="group">
              <th
                scope="row"
                className="sticky left-0 z-10 truncate bg-card px-2 py-0.5 text-left font-medium text-ink group-hover:bg-teal-soft/40"
                title={row.label}
              >
                {row.heading ?? row.label}
              </th>
              {row.cells.map((cell, index) => {
                const bucket = buckets[index];
                if (!bucket) return null;
                return (
                  <td key={bucket.key} className="p-[1.5px]">
                    <div
                      title={cellTitle(cell, bucket, row.label, timezone)}
                      className={`h-5 w-full rounded-[2px] ${cellFill(
                        cell,
                        maxRecords,
                      )}`}
                    />
                  </td>
                );
              })}
              <td className="truncate px-2 py-0.5 text-right tabular-nums text-sage">
                {NUMBER.format(row.records)}
                {row.note ? (
                  <span className="ml-1.5 text-[12px] text-sage/70">{row.note}</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What each colour claims, beside the grid. */
export function CoverageLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-sage">
      {BAND_LEGEND.map((entry) => (
        <span key={entry.band} className="flex items-center gap-1.5">
          <span className={`h-3.5 w-3.5 shrink-0 rounded-[2px] ${entry.fill}`} />
          {entry.label}
        </span>
      ))}
    </div>
  );
}
