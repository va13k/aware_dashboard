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
 * | `blank`    | wash    | nothing was expected — outside every enrolment      |
 * | `none`     | white   | expected, and nothing arrived                       |
 * | `short`    | red     | well under the configured rate                      |
 * | `moderate` | yellow  | approaching the configured rate                     |
 * | `expected` | green   | at the configured rate                              |
 * | `over`     | blue    | far above the configured rate                       |
 *
 * A seventh outcome sits outside the scale. An event sensor — `calls`, `screen`,
 * `messages` — has no configured rate, so a count of its rows compares to nothing
 * and reads as neither short nor excessive. Those buckets take a neutral shade in
 * three steps of volume, which keeps them readable while leaving the six judged
 * colours to mean exactly what they say.
 *
 * Both grids and the legend read the bands from here, so a colour on screen and
 * its entry in the key cannot come to disagree.
 */

/**
 * Two boundaries live here, and only two. The API already decides where a bucket
 * meets the configured rate — it returns `reporting` or `under` — so that
 * threshold is read from its answer rather than restated. What the API has no
 * opinion on is how far short is worth its own colour, and how far above is
 * worth another, which is what these two split.
 */
/** Below this share of the expectation, short becomes its own colour. */
export const SHORT_BELOW = 0.5;
/** Above this multiple of the expectation, a bucket reads as far over. */
export const FAR_OVER = 2;

export type CoverageBand =
  | "blank"
  | "none"
  | "short"
  | "moderate"
  | "expected"
  | "over"
  | "unjudged";

function share(cell: CoverageCell): number | null {
  if (cell.expected == null || cell.expected <= 0) return null;
  return cell.records / cell.expected;
}

/** Where a bucket falls, given what arrived and what was asked for. */
export function bandOf(cell: CoverageCell): CoverageBand {
  // The aggregate cell counts required sensors reporting rather than records, so
  // its share is a fraction of what the study asked for and never exceeds it.
  // Every boundary on it is drawn here, the API carrying only the two counts.
  if (cell.required != null) {
    if (cell.state === "not_expected") return "blank";
    if (!cell.required || !cell.reporting) return "none";
    const reported = cell.reporting / cell.required;
    if (reported < SHORT_BELOW) return "short";
    if (reported < 1) return "moderate";
    return "expected";
  }

  switch (cell.state) {
    case "not_expected":
      return "blank";
    case "missing":
      return "none";
    // Records arrived with no configured rate behind them.
    case "present":
      return "unjudged";
    case "under": {
      const ratio = share(cell);
      return ratio != null && ratio < SHORT_BELOW ? "short" : "moderate";
    }
    case "reporting": {
      const ratio = share(cell);
      return ratio != null && ratio > FAR_OVER ? "over" : "expected";
    }
  }
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

/** What each colour means, for the key beside a grid. */
export const BAND_LEGEND: { band: CoverageBand; fill: string; label: string }[] = [
  { band: "short", fill: BAND_FILL.short, label: "Well under expected" },
  { band: "moderate", fill: BAND_FILL.moderate, label: "Approaching expected" },
  { band: "expected", fill: BAND_FILL.expected, label: "As configured" },
  { band: "over", fill: BAND_FILL.over, label: "Far above expected" },
  { band: "none", fill: BAND_FILL.none, label: "Nothing arrived" },
  { band: "blank", fill: BAND_FILL.blank, label: "Nothing expected" },
  { band: "unjudged", fill: "bg-plain/70", label: "Arrived · no configured rate" },
];
