// Sensor threshold presets, in the same shape as the sampling-frequency
// presets in SensorData.jsx: each option names a use case and states the value
// plus the tradeoff behind it.
//
// A threshold is a change filter, not a cutoff on the reading itself. The
// Android client compares each reading against the last one it STORED, not the
// last one it saw, and stores the new reading only if they differ by at least
// the threshold, in the sensor's own native unit. Slow drift therefore still
// accumulates until it crosses the threshold. On the three-axis sensors a
// sample is dropped only when EVERY axis moved less than the threshold, so
// movement on any single axis still produces a row - the filter suppresses
// stillness, not motion. A threshold of 0 disables filtering and stores every
// sample the sampling frequency yields.
//
// `warnAbove` is the largest value that still leaves the sensor recording
// usefully: it is set to the biggest change the sensor produces in normal use.
// Past it, readings essentially never differ by that much, so every sample is
// filtered out and the sensor goes silent while still appearing enabled -
// which is what a threshold of 120 m/s² or 1,000,000 µT does.
//
// Tier values are anchored to published smartphone sensor-noise figures and to
// the size of the phenomenon being measured, so a threshold can be chosen
// against something real rather than guessed:
//  [MEMS-Noise]   Sensors 23(17):7609 (2023), laboratory characterisation of
//                 five smartphones: per-axis accelerometer noise standard
//                 deviation 0.0042-0.0106 m/s², gyroscope three-axis average
//                 noise standard deviation up to 0.0027 rad/s
//  [Baro-Floor]   Barometric floor-localisation work (PMC6720727; Geo-spatial
//                 Information Science 2019): ~0.43 hPa between adjacent
//                 floors, ~0.13 hPa variation within one floor, 0.12 hPa per
//                 metre of height, 0.06-0.18 hPa per 2 s of stair walking,
//                 0.01 hPa sensor resolution
//  [Mag-Field]    Magnetic-field indoor-positioning literature: ~1 µT
//                 quantisation step, about 2% of Earth's field (23-62 µT)
//  [Light-Level]  PLOS One 2021 ambient-light survey (indoor median 179 lux,
//                 range 50-333; outdoor median 1175 lux) and PLOS Biology 2022
//                 circadian guidance (>=250 lux daytime, <=10 lux evening)
//  [Weber]        Weber-Fechner law: the smallest noticeable change in
//                 intensity grows with the intensity itself, so no single
//                 fixed lux step suits both a dim bedroom and daylight

const OFF = {
  key: "off",
  value: 0,
  label: "Record every sample (no filtering)",
};

// Accelerometer and linear accelerometer share this table. They differ by the
// gravity component, which is constant while the device is still, so the
// change between consecutive samples - the only thing a threshold sees - has
// the same noise floor and the same meaning on both.
const ACCELEROMETER_PRESETS = [
  {
    ...OFF,
    detail:
      "Required for activity recognition, gait analysis and fall detection: those methods need the continuous waveform, including its flat stretches.",
  },
  {
    key: "noise_gate",
    value: 0.05,
    label: "Drop sensor noise only",
    detail:
      "0.05 m/s² - about five times the worst per-axis noise measured across five smartphones (0.0042-0.0106 m/s²) [MEMS-Noise]. Removes rows where nothing but sensor noise changed and keeps everything the participant did.",
  },
  {
    key: "movement",
    value: 0.3,
    label: "Movement vs. stillness",
    detail:
      "0.3 m/s² - keeps device movement, drops a phone resting on a desk or sitting still in a pocket. Suited to movement/no-movement questions; not safe for anything that depends on waveform shape.",
  },
  {
    key: "pronounced",
    value: 1.0,
    label: "Pronounced motion only",
    detail:
      "1.0 m/s² - records walking, gestures and vehicle bumps. Expect long gaps whenever the phone is stationary, and note that those gaps look identical to the sensor not working.",
  },
];

// Gravity is an orientation signal: its vector only moves when the device
// tilts, so the tiers are stated as tilt angles.
const GRAVITY_PRESETS = [
  {
    ...OFF,
    detail:
      "Records the full orientation trace, including periods when the device is held still.",
  },
  {
    key: "noise_gate",
    value: 0.05,
    label: "Drop sensor noise only",
    detail:
      "0.05 m/s² - a noise-level gate [MEMS-Noise]; starting from horizontal this is roughly a 0.3° tilt.",
  },
  {
    key: "tilt",
    value: 0.2,
    label: "Tilt changes",
    detail:
      "0.2 m/s² - roughly a 1° tilt. Keeps deliberate reorientation, drops a device lying still.",
  },
  {
    key: "reorientation",
    value: 1.0,
    label: "Large reorientation only",
    detail:
      "1.0 m/s² - roughly a 6° tilt; records only substantial changes such as picking the phone up or turning it face down.",
  },
];

const GYROSCOPE_PRESETS = [
  {
    ...OFF,
    detail:
      "Required if you integrate angular velocity into orientation: integration needs every sample, including the small ones.",
  },
  {
    key: "noise_gate",
    value: 0.01,
    label: "Drop sensor noise only",
    detail:
      "0.01 rad/s - about four times the worst three-axis noise average measured on smartphones (0.0027 rad/s) [MEMS-Noise]. Removes readings taken while the device was not turning at all.",
  },
  {
    key: "rotation",
    value: 0.05,
    label: "Deliberate rotation",
    detail:
      "0.05 rad/s (about 2.9°/s) - keeps intentional rotation, drops a stationary device and its bias drift.",
  },
  {
    key: "brisk",
    value: 0.2,
    label: "Brisk rotation only",
    detail:
      "0.2 rad/s (about 11°/s) - records only fast turning. Angles integrated from data filtered this hard will drift badly, because the dropped small rotations are exactly what integration needs.",
  },
];

// The rotation vector's stored components are unitless quaternion parts in
// -1…1. For a small rotation of angle θ a component moves by about θ/2, so
// 0.01 is roughly 1.1°.
const ROTATION_PRESETS = [
  {
    ...OFF,
    detail: "Records the full orientation trace.",
  },
  {
    key: "noise_gate",
    value: 0.005,
    label: "Drop sensor noise only",
    detail:
      "0.005 - the components are unitless quaternion parts in -1…1, so this is roughly 0.6° of rotation. A noise-level gate.",
  },
  {
    key: "orientation",
    value: 0.02,
    label: "Orientation changes",
    detail:
      "0.02 - roughly 2° of rotation. Keeps orientation changes worth noting, drops a still device.",
  },
  {
    key: "coarse",
    value: 0.1,
    label: "Coarse orientation states only",
    detail:
      "0.1 - roughly 11° of rotation; enough to tell broad postures apart and nothing finer.",
  },
];

const MAGNETOMETER_PRESETS = [
  {
    ...OFF,
    detail:
      "Required for magnetic-fingerprint indoor positioning, which depends on exactly the small spatial variation a threshold removes.",
  },
  {
    key: "noise_gate",
    value: 1,
    label: "Drop sensor noise only",
    detail:
      "1 µT - one quantisation step on a typical smartphone magnetometer, about 2% of Earth's field of 23-62 µT [Mag-Field]. Removes readings that did not resolvably change.",
  },
  {
    key: "heading",
    value: 3,
    label: "Heading and environment changes",
    detail:
      "3 µT - keeps genuine heading and surroundings changes, drops a still device. Too coarse for magnetic fingerprinting.",
  },
  {
    key: "disturbance",
    value: 10,
    label: "Strong disturbances only",
    detail:
      "10 µT - records only large magnetic events such as passing metal structures, vehicles or magnets.",
  },
];

const BAROMETER_PRESETS = [
  {
    ...OFF,
    detail:
      "Records the full pressure trace, including slow weather drift, at the cost of many near-identical rows.",
  },
  {
    key: "noise_gate",
    value: 0.02,
    label: "Drop sensor noise only",
    detail:
      "0.02 hPa - twice the sensor's 0.01 hPa resolution [Baro-Floor]. Removes readings that did not resolvably change while keeping weather drift and all vertical movement.",
  },
  {
    key: "vertical",
    value: 0.05,
    label: "Vertical movement",
    detail:
      "0.05 hPa - about 0.4 m of height, below the 0.06-0.18 hPa that two seconds of stair walking produces [Baro-Floor], so stairs and lifts are still captured but a stationary device is not.",
  },
  {
    key: "floor",
    value: 0.4,
    label: "Floor transitions only",
    detail:
      "0.4 hPa - about one floor: adjacent floors differ by roughly 0.43 hPa, with about 0.13 hPa of variation within a single floor [Baro-Floor]. Weather trends and individual steps are lost.",
  },
];

// Illuminance spans five orders of magnitude, so a fixed lux step cannot be
// right at both ends of the range [Weber]. That makes 0 the safe choice far
// more often here than on the other sensors.
const LIGHT_PRESETS = [
  {
    ...OFF,
    detail:
      "Recommended for circadian, sleep and screen-exposure research: the evening levels those questions turn on are around 10 lux [Light-Level], and any larger fixed threshold erases them.",
  },
  {
    key: "noise_gate",
    value: 1,
    label: "Drop sensor noise only",
    detail:
      "1 lux - removes readings that barely moved while preserving the low-light range circadian guidance is stated in (10 lux or less in the evening, 250 lux or more in daytime) [Light-Level].",
  },
  {
    key: "indoor",
    value: 10,
    label: "Indoor lighting changes",
    detail:
      "10 lux - keeps changes in indoor lighting, which runs about 50-333 lux [Light-Level]. Erases all variation below 10 lux, so evening and night-time light is effectively no longer measured.",
  },
  {
    key: "transition",
    value: 50,
    label: "Room and indoor/outdoor transitions only",
    detail:
      "50 lux - records gross transitions and nothing else. Because a noticeable change scales with brightness [Weber], one fixed step is coarse at night and invisible in daylight; prefer 0 or 1 unless gross transitions are genuinely all you need.",
  },
];

const TEMPERATURE_PRESETS = [
  {
    ...OFF,
    detail:
      "Records every sample, which on a slow-moving signal like ambient temperature means many identical rows.",
  },
  {
    key: "noise_gate",
    value: 0.1,
    label: "Drop sensor noise only",
    detail:
      "0.1 °C - the resolution of a typical ambient-temperature sensor. Removes readings that did not resolvably change.",
  },
  {
    key: "environmental",
    value: 0.5,
    label: "Environmental changes",
    detail:
      "0.5 °C - ambient temperature moves over minutes, so this keeps real changes such as stepping outdoors or heating switching on at a fraction of the row count.",
  },
];

// Proximity hardware reports two quantised states on most devices - near
// (about 0 cm) and far (about 5 cm) - and usually only when that state
// changes. There is nothing in between for a threshold to filter, so the only
// defensible setting is 0.
const PROXIMITY_PRESETS = [
  {
    ...OFF,
    label: "Record every near/far change (recommended)",
    detail:
      "Most proximity hardware reports only two states, near at about 0 cm and far at about 5 cm, and reports them only on change. There are no intermediate readings for a threshold to remove, and any threshold above the near/far step silences the sensor completely.",
  },
];

// Keyed by the Configurator's sensor mode name, so a call site passes one
// string and gets the unit, the physical limit and the presets together.
export const THRESHOLDS = {
  accelerometer: {
    label: "accelerometer",
    unit: "m/s²",
    axes: 3,
    warnAbove: 20,
    presets: ACCELEROMETER_PRESETS,
  },
  linearAccelerometer: {
    label: "linear accelerometer",
    unit: "m/s²",
    axes: 3,
    warnAbove: 20,
    presets: ACCELEROMETER_PRESETS,
  },
  gravity: {
    label: "gravity",
    unit: "m/s²",
    axes: 3,
    warnAbove: 9.81,
    presets: GRAVITY_PRESETS,
  },
  gyroscope: {
    label: "gyroscope",
    unit: "rad/s",
    axes: 3,
    // 5 rad/s is about 286°/s, already past anything normal handling produces.
    warnAbove: 5,
    presets: GYROSCOPE_PRESETS,
  },
  rotation: {
    label: "rotation",
    unit: "quaternion units",
    axes: 3,
    warnAbove: 1,
    presets: ROTATION_PRESETS,
  },
  magnetometer: {
    label: "magnetometer",
    unit: "µT",
    axes: 3,
    warnAbove: 100,
    presets: MAGNETOMETER_PRESETS,
  },
  barometer: {
    label: "barometer",
    unit: "hPa",
    axes: 1,
    // 5 hPa is about 40 m of height, or a whole weather system passing.
    warnAbove: 5,
    presets: BAROMETER_PRESETS,
  },
  light: {
    label: "light",
    unit: "lux",
    axes: 1,
    warnAbove: 10000,
    presets: LIGHT_PRESETS,
  },
  temperature: {
    label: "temperature",
    unit: "°C",
    axes: 1,
    warnAbove: 10,
    presets: TEMPERATURE_PRESETS,
  },
  proximity: {
    label: "proximity",
    unit: "cm",
    axes: 1,
    warnAbove: 5,
    presets: PROXIMITY_PRESETS,
  },
};

// The explanation shown under every threshold field. It states the filter's
// direction and its per-axis rule, because both are easy to get backwards and
// getting them backwards is how a sensor ends up silently collecting nothing.
export function thresholdDescription(sensor) {
  const spec = THRESHOLDS[sensor];
  if (!spec) return "";

  const axisRule =
    spec.axes === 3
      ? " A sample is dropped only when all three axes changed by less than the threshold, so movement on any single axis is still recorded."
      : "";

  return `A reading is stored only when it differs from the last stored reading by at least this much, in ${spec.unit}.${axisRule} 0 stores every sample. Values above ${spec.warnAbove} (${spec.unit}) exceed the changes this sensor sees in normal use, so almost nothing would be recorded while the sensor still shows as enabled.`;
}
