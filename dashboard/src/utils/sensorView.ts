import { useEffect, useState } from "react";

/**
 * How the sensor grids are filtered, shared by the overview and the per-device
 * view so the two never drift apart.
 *
 * - `all`      every sensor the platform can report
 * - `records`  only sensors that already have data
 * - `required` only sensors the deployed config asks the phone to record
 */
export type SensorView = "all" | "records" | "required";

// Same key the old boolean checkbox used, so a returning user keeps their
// preference. The value used to be "true"/"false"; it is migrated on read.
const STORAGE_KEY = "aware-dashboard-hide-empty-sensors";

export function readSensorView(): SensorView {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === "all" || raw === "records" || raw === "required") return raw;
  // "Hide empty sensors" was the only filter before, so a phone that had it on
  // wanted the records-only view; everything else defaults to showing all.
  if (raw === "true") return "records";
  return "all";
}

/** State bound to the shared localStorage key, with the old value migrated. */
export function useSensorView(): [SensorView, (view: SensorView) => void] {
  const [view, setView] = useState<SensorView>(readSensorView);
  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, view);
  }, [view]);
  return [view, setView];
}
