import type { CoverageBucket, CoverageCell } from "../types";

/**
 * The coverage grid: one row per device or per sensor, one column per bucket.
 *
 * What the view is for is seeing *how and when* data arrives — so volume is what
 * the colour carries, on one sequential ramp shared by every row. Two cells of
 * the same shade hold the same amount of data, which is the only claim a heatmap
 * makes and the reason the ceiling is decided per grid rather than per row.
 *
 * A single-hue ramp, for two reasons. Its steps differ in lightness as well as
 * hue, so the order survives without colour vision. And it says how much arrived
 * and leaves why to the reader: a quiet stretch is usually just a quiet stretch —
 * a participant asleep, a phone in a pocket, an event sensor with nothing to
 * report — so the comparison with the study config sits in the hover detail,
 * beside the count it was made against.
 *
 * One distinction earns its own appearance. A bucket where nothing was expected —
 * before the phone joined, in the gap after it quit, after it withdrew — is drawn
 * as a neutral wash, and an expected bucket that stayed empty is drawn as an
 * outlined cell. Telling those two apart is what the enrolment windows are for.
 */

/** Where a cell's shade sits on the ramp, by its share of the grid's busiest. */
function shadeOf(records: number, ceiling: number): string {
  if (records <= 0) return "";
  if (ceiling <= 0) return "bg-teal/70";
  // Five steps on a square-root scale: record counts span orders of magnitude
  // between sensors, and a linear ramp would put everything but the busiest
  // sensor in the palest step.
  const share = Math.sqrt(records / ceiling);
  if (share >= 0.85) return "bg-teal";
  if (share >= 0.6) return "bg-teal/80";
  if (share >= 0.4) return "bg-teal/60";
  if (share >= 0.2) return "bg-teal/40";
  return "bg-teal/25";
}

function cellClass(cell: CoverageCell, ceiling: number): string {
  if (cell.state === "not_expected") {
    // Nothing was asked of this bucket. A faint wash keeps the grid's alignment
    // readable through a long run of them, so a reader can still see which
    // column they are looking at.
    return "bg-ink/4";
  }
  if (cell.records <= 0) {
    // Expected and empty. An outline says the bucket exists and is bare, which
    // is what separates a quiet sensor from one nobody asked for.
    return "bg-card-strong ring-1 ring-inset ring-wire";
  }
  return shadeOf(cell.records, ceiling);
}

const NUMBER = new Intl.NumberFormat();

function bucketRange(bucket: CoverageBucket, timezone: string): string {
  const format = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  });
  return `${format.format(bucket.from)} — ${format.format(bucket.to)}`;
}

/** What hovering a cell says, in the order a reader needs it. */
function cellTitle(
  cell: CoverageCell,
  bucket: CoverageBucket,
  rowLabel: string,
  timezone: string,
): string {
  const lines = [`${rowLabel} · ${bucketRange(bucket, timezone)}`];

  if (cell.state === "not_expected") {
    lines.push("Nothing expected — outside this device's enrolment.");
    return lines.join("\n");
  }

  if (cell.required != null) {
    lines.push(
      `${cell.reporting} of ${cell.required} required sensors reported`,
      `${NUMBER.format(cell.records ?? 0)} records`,
    );
    return lines.join("\n");
  }

  lines.push(`${NUMBER.format(cell.records)} records`);

  if (cell.expected != null) {
    const verb = cell.floor ? "at least" : "about";
    lines.push(`Config implies ${verb} ${NUMBER.format(Math.round(cell.expected))}`);
    if (cell.floor) {
      lines.push("That figure bounds the scans, not the rows each one yields.");
    }
  } else if (cell.basis === "event") {
    lines.push("Event sensor — no configured rate to expect.");
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
  /** Rendered instead of `label` when the row heading needs more than text. */
  heading?: React.ReactNode;
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
      <div className="rounded-xl border border-wire bg-card p-6 text-center text-[13px] text-sage">
        {emptyMessage}
      </div>
    );
  }

  const drillable = onColumnClick != null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-[11px]">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-card px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-[0.4px] text-sage">
              {rowHeader}
            </th>
            {buckets.map((bucket) => (
              <th key={bucket.key} className="px-0 pb-1 align-bottom">
                {drillable ? (
                  <button
                    type="button"
                    onClick={() => onColumnClick?.(bucket)}
                    title={`Open ${bucketRange(bucket, timezone)}`}
                    className="w-full cursor-pointer rounded px-0.5 text-[9px] font-medium text-sage transition-colors hover:text-teal"
                  >
                    {bucket.label}
                  </button>
                ) : (
                  <span className="block text-[9px] font-medium text-sage">
                    {bucket.label}
                  </span>
                )}
              </th>
            ))}
            <th className="px-2 pb-1 text-right text-[10px] font-semibold uppercase tracking-[0.4px] text-sage">
              Records
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="group">
              <th
                scope="row"
                className="sticky left-0 z-10 max-w-[190px] truncate bg-card px-2 py-0.5 text-left font-medium text-ink group-hover:bg-teal-soft/40"
                title={row.label}
              >
                {row.heading ?? row.label}
              </th>
              {row.cells.map((cell, index) => {
                const bucket = buckets[index];
                if (!bucket) return null;
                return (
                  <td key={bucket.key} className="p-[1px]">
                    <div
                      title={cellTitle(cell, bucket, row.label, timezone)}
                      className={`h-4 w-full min-w-[9px] rounded-[2px] ${cellClass(
                        cell,
                        maxRecords,
                      )} ${
                        // A shortfall against the configured rate is marked, not
                        // coloured: worth spotting while scanning, not worth
                        // shouting about.
                        cell.state === "under"
                          ? "border-b-2 border-b-ink/25"
                          : ""
                      }`}
                    />
                  </td>
                );
              })}
              <td className="whitespace-nowrap px-2 py-0.5 text-right tabular-nums text-sage">
                {NUMBER.format(row.records)}
                {row.note ? (
                  <span className="ml-1 text-[9px] text-sage/70">{row.note}</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What the shades and the two structural states mean, beside the grid. */
export function CoverageLegend({ maxRecords }: { maxRecords: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[10px] text-sage">
      <span className="flex items-center gap-1.5">
        Fewer
        <span className="flex gap-[2px]">
          {["bg-teal/25", "bg-teal/40", "bg-teal/60", "bg-teal/80", "bg-teal"].map(
            (shade) => (
              <span key={shade} className={`h-3 w-3 rounded-[2px] ${shade}`} />
            ),
          )}
        </span>
        More
        {maxRecords > 0 ? (
          <span className="tabular-nums">
            (up to {NUMBER.format(maxRecords)})
          </span>
        ) : null}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-[2px] bg-card-strong ring-1 ring-inset ring-wire" />
        Nothing arrived
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-[2px] bg-ink/4" />
        Nothing expected
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-[2px] bg-teal/40 border-b-2 border-b-ink/25" />
        Below the configured rate
      </span>
    </div>
  );
}
