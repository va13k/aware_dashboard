/**
 * Which timezone a coverage grid's buckets are cut in.
 *
 * It matters because the grid is read as an account of a participant's day. Hours
 * are stored in UTC, and cutting them into local days is what puts a night in the
 * middle of a row where a researcher can recognise it as one — in Zurich that
 * moves every column two hours, and a sleep gap lands whole instead of split
 * across the boundary between two grids.
 *
 * The offer is short on purpose: the browser's own zone, UTC, and whatever the
 * link being followed already carried. A full IANA list is a long menu answering
 * a question a researcher asks once, and the server accepts any zone name, so a
 * shared link naming one outside the list still opens in it.
 */

import { browserTimezone } from "../utils/time";

/** The local zone offset as a reader recognises it, e.g. `UTC+2`. */
function offsetLabel(zone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    return parts.find((part) => part.type === "timeZoneName")?.value ?? "";
  } catch {
    return "";
  }
}

export default function TimezonePicker({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (zone: string) => void;
  className?: string;
}) {
  const local = browserTimezone();
  const offered = [...new Set([local, "UTC", value])];

  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={className}
      title="The timezone the columns are cut in"
    >
      {offered.map((zone) => (
        <option key={zone} value={zone}>
          {zone === local && zone !== "UTC" ? `${zone} (here)` : zone}
          {zone === "UTC" ? "" : ` · ${offsetLabel(zone)}`}
        </option>
      ))}
    </select>
  );
}
