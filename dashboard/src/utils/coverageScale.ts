import type { CoverageCell } from "../types";

/**
 * What colour a coverage cell takes, and what that colour claims.
 *
 * The scale is diverging rather than sequential: it reads a bucket against what
 * the study config asked for, so the eye lands on the sensors that came in short
 * without reading a count. Six outcomes, in the order a reader meets them.
 *
 * | band       | colour  | meaning                                            |
 * | ---------- | ------- | -------------------------------------------------- |
 * | `blank`    | wash    | nothing was expected, and nothing arrived           |
 * | `none`     | white   | expected, and nothing arrived                       |
 * | `short`    | red     | well under the configured rate                      |
 * | `moderate` | yellow  | approaching the configured rate                     |
 * | `expected` | green   | at the configured rate                              |
 * | `over`     | blue    | far above the configured rate                       |
 *
 * A seventh outcome sits outside the scale: rows that arrived with nothing to
 * measure them against. An event sensor — `calls`, `screen`, `messages` — has no
 * configured rate, so a count of its rows compares to nothing and reads as neither
 * short nor excessive. A bucket outside every enrolment window lands here too: a
 * phone still uploading after it left the study asked nothing of it, so there is
 * no expectation to judge the count by — but the rows are there and the grid says
 * so, rather than showing the empty bucket its totals would then contradict.
 * Those buckets take a neutral shade in three steps of volume, which keeps them
 * readable while leaving the six judged colours to mean exactly what they say.
 *
 * The bands themselves are decided by the API (`services/coverage_matrix.py`);
 * what lives here is which colour each one wears. Both grids and the legend read
 * it from here, so a colour on screen and its entry in the key cannot disagree.
 *
 * The all-sensors grid wears these colours for a different measurement: its band
 * counts how many of the required sensors reported, not how much one of them
 * sent. `AGGREGATE_BAND_LEGEND` is what they claim there.
 */

export type CoverageBand =
  | "blank"
  | "none"
  | "short"
  | "moderate"
  | "expected"
  | "over"
  | "unjudged";

const BANDS = new Set<string>([
  "blank",
  "none",
  "short",
  "moderate",
  "expected",
  "over",
  "unjudged",
]);

/**
 * Which band a cell falls in, as the API decided.
 *
 * Sent with the cell rather than worked out here, because the downloadable
 * workbook is coloured server-side from the same figure. Two implementations of
 * the boundaries would let a cell come out red on screen and green in the
 * spreadsheet a researcher circulates.
 *
 * `state` is the fallback for a response predating the band, and covers the two
 * cases a colour must never get wrong: nothing expected, and nothing arrived.
 */
export function bandOf(cell: CoverageCell): CoverageBand {
  if (cell.band && BANDS.has(cell.band)) return cell.band as CoverageBand;
  if (cell.state === "not_expected") return "blank";
  if (cell.state === "missing") return "none";
  return cell.records > 0 ? "unjudged" : "none";
}

/** Three steps of neutral for a bucket with no rate behind it. */
function unjudgedShade(records: number, ceiling: number): string {
  if (ceiling <= 0) return "bg-plain";
  const share = Math.sqrt(records / ceiling);
  if (share >= 0.66) return "bg-plain";
  if (share >= 0.33) return "bg-plain/70";
  return "bg-plain/40";
}

const BAND_FILL: Record<Exclude<CoverageBand, "unjudged">, string> = {
  blank: "bg-ink/4",
  none: "bg-white ring-1 ring-inset ring-wire",
  short: "bg-short",
  moderate: "bg-moderate",
  expected: "bg-expected",
  over: "bg-over",
};

/** The classes painting one cell. */
export function cellFill(cell: CoverageCell, ceiling: number): string {
  const band = bandOf(cell);
  if (band === "unjudged") return unjudgedShade(cell.records, ceiling);
  return BAND_FILL[band];
}

/** What each colour means, for the key beside a single sensor's grid. */
export const BAND_LEGEND: { band: CoverageBand; fill: string; label: string }[] = [
  { band: "short", fill: BAND_FILL.short, label: "Well under expected" },
  { band: "moderate", fill: BAND_FILL.moderate, label: "Approaching expected" },
  { band: "expected", fill: BAND_FILL.expected, label: "As configured" },
  { band: "over", fill: BAND_FILL.over, label: "Far above expected" },
  { band: "none", fill: BAND_FILL.none, label: "Nothing arrived" },
  { band: "blank", fill: BAND_FILL.blank, label: "Nothing expected" },
  { band: "unjudged", fill: "bg-plain/70", label: "Arrived · nothing to judge by" },
];

/**
 * The same colours, for the grid showing every required sensor at once.
 *
 * There the band comes from `aggregate_band`, which counts how many of the
 * required sensors reported anything rather than how much any one of them sent.
 * The scale carries no `over`, because a share of what the study asked for cannot
 * exceed it. One colour meaning two things needs two keys: red on a sensor grid is
 * a stream running below its configured rate, and red here is a phone reporting
 * under half the sensors the study asked for.
 */
export const AGGREGATE_BAND_LEGEND: {
  band: CoverageBand;
  fill: string;
  label: string;
}[] = [
  { band: "short", fill: BAND_FILL.short, label: "Under half the sensors reported" },
  { band: "moderate", fill: BAND_FILL.moderate, label: "Most sensors reported" },
  { band: "expected", fill: BAND_FILL.expected, label: "Every sensor reported" },
  { band: "none", fill: BAND_FILL.none, label: "No sensor reported" },
  { band: "blank", fill: BAND_FILL.blank, label: "Nothing expected" },
  {
    band: "unjudged",
    fill: "bg-plain/70",
    label: "Arrived · outside the enrolment",
  },
];
