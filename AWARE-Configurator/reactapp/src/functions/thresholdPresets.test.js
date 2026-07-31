import { THRESHOLDS, thresholdDescription } from "./thresholdPresets";

// The ten sensors whose Android settings include a threshold_<sensor> key.
// Kept explicit so adding a sensor to one side without the other fails here
// rather than silently shipping a threshold field with no guidance.
const SENSORS_WITH_THRESHOLDS = [
  "accelerometer",
  "barometer",
  "gravity",
  "gyroscope",
  "light",
  "linearAccelerometer",
  "magnetometer",
  "proximity",
  "rotation",
  "temperature",
];

describe("THRESHOLDS", () => {
  test("covers exactly the sensors that have a threshold setting", () => {
    expect(Object.keys(THRESHOLDS).sort()).toEqual(
      [...SENSORS_WITH_THRESHOLDS].sort()
    );
  });

  test.each(SENSORS_WITH_THRESHOLDS)(
    "%s declares a unit and a limit",
    (sensor) => {
      const spec = THRESHOLDS[sensor];
      expect(spec.label).toBeTruthy();
      expect(spec.unit).toBeTruthy();
      expect([1, 3]).toContain(spec.axes);
      expect(spec.warnAbove).toBeGreaterThan(0);
    }
  );

  test.each(SENSORS_WITH_THRESHOLDS)(
    "%s offers unfiltered collection first",
    (sensor) => {
      const [first] = THRESHOLDS[sensor].presets;
      expect(first.key).toBe("off");
      expect(first.value).toBe(0);
    }
  );

  test.each(SENSORS_WITH_THRESHOLDS)(
    "%s presets are labelled and justified",
    (sensor) => {
      THRESHOLDS[sensor].presets.forEach((preset) => {
        expect(preset.key).toBeTruthy();
        expect(preset.label).toBeTruthy();
        expect(preset.detail).toBeTruthy();
      });
    }
  );

  test.each(SENSORS_WITH_THRESHOLDS)("%s preset keys are unique", (sensor) => {
    const keys = THRESHOLDS[sensor].presets.map((preset) => preset.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  test.each(SENSORS_WITH_THRESHOLDS)("%s presets increase from 0", (sensor) => {
    const values = THRESHOLDS[sensor].presets.map((preset) => preset.value);
    expect(values).toEqual([...values].sort((a, b) => a - b));
    expect(new Set(values).size).toBe(values.length);
  });

  // A preset that exceeds the sensor's own range would silence the sensor,
  // which is the failure these presets exist to prevent.
  test.each(SENSORS_WITH_THRESHOLDS)(
    "%s presets stay inside the sensor's range",
    (sensor) => {
      const spec = THRESHOLDS[sensor];
      spec.presets.forEach((preset) => {
        expect(preset.value).toBeLessThanOrEqual(spec.warnAbove);
      });
    }
  );
});

// The values below were live in a deployed study configuration. Each exceeds
// the change its sensor sees in normal use, so the sensor filtered out
// effectively every sample and recorded nothing while still reporting itself
// as enabled.
describe("limits reject the values from the deployed study config", () => {
  const DEPLOYED = {
    accelerometer: 120,
    linearAccelerometer: 100,
    gravity: 10,
    gyroscope: 10,
    rotation: 10,
    magnetometer: 1000000,
    proximity: 10,
    barometer: 10,
    temperature: 100,
  };

  test.each(Object.entries(DEPLOYED))(
    "%s threshold of %s is out of range",
    (sensor, value) => {
      expect(value).toBeGreaterThan(THRESHOLDS[sensor].warnAbove);
    }
  );

  // Light is the one exception: illuminance does swing by hundreds of lux, so
  // the deployed 100 was not impossible, only coarser than any tier worth
  // recommending - it discards everything below 100 lux, which is the whole
  // evening and night-time range.
  test("light threshold of 100 is within range but coarser than every preset", () => {
    const spec = THRESHOLDS.light;
    expect(100).toBeLessThanOrEqual(spec.warnAbove);
    const coarsest = Math.max(...spec.presets.map((preset) => preset.value));
    expect(100).toBeGreaterThan(coarsest);
  });
});

describe("thresholdDescription", () => {
  test("states the unit, the zero case and the limit", () => {
    const text = thresholdDescription("accelerometer");
    expect(text).toContain("m/s²");
    expect(text).toContain("0 stores every sample");
    expect(text).toContain("20");
  });

  test("explains the per-axis rule only for three-axis sensors", () => {
    expect(thresholdDescription("gyroscope")).toContain("all three axes");
    expect(thresholdDescription("light")).not.toContain("all three axes");
  });

  test("returns nothing for a sensor without a threshold", () => {
    expect(thresholdDescription("wifi")).toBe("");
  });
});
