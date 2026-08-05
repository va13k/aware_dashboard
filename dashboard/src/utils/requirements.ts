import type { PlatformRequirements, StudyRequirements } from "../types";

/**
 * The requirements one sensor view needs, flattened from the API's per-platform
 * shape: which stream keys the deployed config asks a phone to record, and which
 * required settings have no stream the dashboard can show.
 */
export interface RequirementLookup {
  /** False when no config was found for the platform(s) this lookup covers. */
  available: boolean;
  /** Stream keys the config requires. */
  required: Set<string>;
  /** Required settings the dashboard has no stream for. */
  requiredWithoutStream: string[];
}

function lookupFrom(
  platform: PlatformRequirements | undefined,
): RequirementLookup {
  if (!platform || !platform.available) {
    return { available: false, required: new Set(), requiredWithoutStream: [] };
  }
  return {
    available: true,
    required: new Set(
      platform.sensors.filter((s) => s.required).map((s) => s.sensor_key),
    ),
    requiredWithoutStream: platform.required_without_stream,
  };
}

/** The requirements for a single platform, for the per-device view. */
export function platformRequirements(
  requirements: StudyRequirements | null,
  platform: "android" | "ios",
): RequirementLookup {
  return lookupFrom(requirements?.[platform]);
}

/**
 * Android and iOS requirements merged, for the overview, where a shared sensor
 * is required if either platform's config asks for it.
 */
export function combinedRequirements(
  requirements: StudyRequirements | null,
): RequirementLookup {
  const android = lookupFrom(requirements?.android);
  const ios = lookupFrom(requirements?.ios);
  return {
    available: android.available || ios.available,
    required: new Set([...android.required, ...ios.required]),
    requiredWithoutStream: [
      ...new Set([
        ...android.requiredWithoutStream,
        ...ios.requiredWithoutStream,
      ]),
    ],
  };
}
