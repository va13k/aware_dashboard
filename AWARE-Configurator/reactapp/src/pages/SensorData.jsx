import "./SensorData.css";
import React from "react";
import Grid from "@mui/material/Unstable_Grid2";
import Box from "@mui/material/Box";
import { useRecoilState } from "recoil";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Checkbox,
  Radio,
  RadioGroup,
  TextField,
  ThemeProvider,
} from "@mui/material";
import FormControlLabel from "@mui/material/FormControlLabel";
import {
  accelerometerState,
  applicationSensorState,
  barometerState,
  bluetoothState,
  communicationSensorState,
  gravityState,
  gyroscopeState,
  lightState,
  linearAccelerometerState,
  locationsState,
  magnetometerState,
  networkState,
  processorState,
  proximityState,
  rotationState,
  screenSensorState,
  sensorDataState,
  studyFormStudyInformationState,
  temperatureState,
  timezoneState,
  wifiState,
  screenshotSensorState,
  noteState,
  pluginSensorState,
} from "../functions/atom";
import SensorComponent from "../components/SensorComponent/SensorComponent";
import FrequencyField from "../components/FrequencyField/FrequencyField";
import customisedTheme from "../functions/theme";
import Field from "../components/Field/Field";
import InputField from "../components/InputField/InputField";
import PluginAPIField from "../components/PluginAPIField/PluginAPIField";
import PasswordField from "../components/PasswordField/PasswordField";

// Sensor sampling-rate presets, grounded in digital-phenotyping / mobile-
// sensing literature rather than an arbitrary evenly-spaced speed scale.
// Each option names the use case it serves and states the tradeoff (battery,
// storage, or missed-event risk) that justifies it. The number of options is
// NOT fixed at five - sensors whose literature only supports two or three
// meaningfully distinct rates get that many, plus Custom. Where no
// phenotyping-specific research exists for a sensor (e.g. processor load),
// the detail text says so explicitly rather than implying a citation that
// isn't there.
//
// Full sources are listed in the accompanying chat response; abbreviated
// citations below refer to the same set:
//  [HAR-review]  npj Digital Medicine 2021 systematic review of smartphone
//                HAR methods for health research
//  [FallDet]     Sensors 2026, "Impact of Accelerometer Sampling Rate on
//                Fall-Detection Model Performance"
//  [GPS-Beiwe]   PMC10020906 + Beiwe platform docs on GPS on/off cycling and
//                battery cost; PMC7868053 on missed-trip rates from sampled
//                GPS traces
//  [BLE-Prox]    Wiley Mobile Information Systems 2020, BLE advertisement-
//                based proximity detection; scan-interval battery studies
//  [Light]       arXiv:2003.06159 on smartphone ambient light sensor
//                practical sampling ceiling (~5 Hz)
//  [IndoorPos]   Sensors 24(11):3367 and related indoor-positioning sensor-
//                fusion literature (gyroscope/magnetometer/barometer use)
//  [StudentLife] Dartmouth StudentLife study + related smartwatch conversation-
//                detection work on audio duty-cycling (short listening windows
//                separated by longer idle periods)
//  [ActivityRec] Google Play Services ActivityRecognitionClient developer
//                documentation on detectionIntervalMillis battery tradeoffs
//  [Fitbit-MH]   Fitbit-based mental-health studies (student mental-health
//                screening, anxiety/stress prediction) that sync at
//                day-level resolution

// Motion/inertial sensors - accelerometer, gravity, gyroscope, linear
// accelerometer, and rotation vector all share this table. They're kept
// consistent with each other because they're typically fused together
// (e.g. gravity + accelerometer, or gyroscope + accelerometer for
// orientation), so sampling them at different rates would misalign the
// fused signal.
const MOTION_PRESETS = [
  {
    key: "fall_impact",
    value: 20000,
    label: "Fall / impact detection",
    detail:
      "50 Hz (20,000 microseconds) - the sensitivity/false-alarm balance point found across fall-detection studies [FallDet]. Highest battery and storage cost of these options.",
  },
  {
    key: "activity_classification",
    value: 50000,
    label: "Activity / transport-mode classification",
    detail:
      "20 Hz (50,000 microseconds) - standard rate in HAR literature for distinguishing walking, running, cycling, vehicle travel [HAR-review].",
  },
  {
    key: "coarse_mobility",
    value: 100000,
    label: "Coarse mobility type",
    detail:
      "10 Hz (100,000 microseconds) - sufficient to distinguish broad mobility categories (still / walking / in-vehicle) [HAR-review]; roughly half the data volume of the tier above.",
  },
  {
    key: "battery_conservative",
    value: 1000000,
    label: "Long-term, battery-conservative",
    detail:
      "1 Hz (1,000,000 microseconds) - only detects gross movement vs. stillness. Recommended when battery life matters more than movement detail, e.g. multi-week passive studies.",
  },
];

// Magnetometer changes more slowly than raw motion and is mainly useful
// fused with gyroscope/accelerometer for heading - it doesn't need
// activity-recognition-grade speed even at its fastest tier.
const MAGNETOMETER_PRESETS = [
  {
    key: "indoor_positioning",
    value: 50000,
    label: "Indoor positioning / heading fusion",
    detail:
      "20 Hz (50,000 microseconds) - needed when fused with gyroscope + accelerometer for real-time dead-reckoning / indoor tracking [IndoorPos].",
  },
  {
    key: "compass_context",
    value: 200000,
    label: "Orientation / compass context",
    detail:
      "5 Hz (200,000 microseconds) - general heading-context sensing without positioning-grade fusion.",
  },
  {
    key: "minimal",
    value: 1000000,
    label: "Minimal footprint",
    detail:
      "1 Hz (1,000,000 microseconds) - coarse orientation only, for long-duration studies.",
  },
];

// Ambient light - the phenomenon of interest for phenotyping (day/night,
// indoor/outdoor, screen-exposure proxy) changes over seconds to minutes,
// not sub-second, even though the sensor hardware itself can be read faster.
const LIGHT_PRESETS = [
  {
    key: "fine_transitions",
    value: 200000,
    label: "Fine environmental transitions",
    detail:
      "5 Hz (200,000 microseconds) - close to the practical ceiling for ambient light sensing on phones [Light]; captures fast transitions like walking indoors/outdoors.",
  },
  {
    key: "circadian_proxy",
    value: 1000000,
    label: "Circadian / screen-exposure proxy",
    detail:
      "1 Hz (1,000,000 microseconds) - the transitions that matter for sleep/circadian research (day/night, indoor/outdoor) happen over seconds to minutes, so faster sampling is oversampling.",
  },
  {
    key: "passive_longterm",
    value: 30000000,
    label: "Long-term passive monitoring",
    detail:
      "Every 30s (30,000,000 microseconds) - minimal battery/storage draw; still captures day/night and location-context light patterns over weeks.",
  },
];

// Barometer is mainly useful fused with accelerometer/gyroscope to detect
// floor changes (stairs/elevator) via the pressure derivative, not as a
// standalone high-rate signal.
const BAROMETER_PRESETS = [
  {
    key: "floor_transition",
    value: 200000,
    label: "Real-time floor / vertical-transition detection",
    detail:
      "5 Hz (200,000 microseconds) - matched to the accelerometer rate it's fused with for stairs/elevator detection in indoor positioning [IndoorPos].",
  },
  {
    key: "elevation_context",
    value: 1000000,
    label: "Coarse elevation / weather context",
    detail:
      "1 Hz (1,000,000 microseconds) - general altitude and pressure-trend logging.",
  },
  {
    key: "minimal",
    value: 30000000,
    label: "Minimal footprint",
    detail:
      "Every 30s (30,000,000 microseconds) - passive environmental logging only.",
  },
];

// Proximity is fundamentally a near/far event sensor (phone-to-ear, pocket),
// not a continuous stream - most hardware reports on state change regardless
// of the requested rate, so it only gets two meaningfully distinct options.
const PROXIMITY_PRESETS = [
  {
    key: "realtime_state",
    value: 200000,
    label: "Real-time call / pocket-state detection",
    detail:
      "5 Hz (200,000 microseconds) - promptly catches phone-to-ear or pocket transitions.",
  },
  {
    key: "standard_context",
    value: 1000000,
    label: "Standard context logging",
    detail:
      "1 Hz (1,000,000 microseconds) - near/far state changes are infrequent; most hardware effectively reports on-change regardless of the requested rate.",
  },
];

// Ambient temperature: a rare hardware sensor on modern phones, and where
// present it tracks slow-moving weather/environment, not anything that
// changes meaningfully faster than tens of seconds. No phenotyping
// literature calls for sub-second sampling here, so this table intentionally
// starts much slower than the other environmental sensors.
const TEMPERATURE_PRESETS = [
  {
    key: "standard",
    value: 10000000,
    label: "Standard environmental logging",
    detail:
      "Every 10s (10,000,000 microseconds) - ambient temperature changes on the order of minutes, so sub-10s sampling adds no information, only battery/storage cost.",
  },
  {
    key: "minimal",
    value: 60000000,
    label: "Minimal footprint",
    detail:
      "Every 60s (60,000,000 microseconds) - matches how slowly this signal actually moves.",
  },
];

// GPS / network location, in seconds. Both location sources share this table
// so they stay consistent with each other. GPS is the single most
// battery-expensive sensor on the phone, and - critically - even reasonably
// frequent sampling misses a large share of short trips, so faster isn't a
// silver bullet.
const LOCATION_PRESETS = [
  {
    key: "trip_capture",
    value: 30,
    label: "Trip / transportation-mode capture",
    detail:
      "30s - common research interval for catching trip start/end [GPS-Beiwe]; even so, published GPS-trace studies still miss a majority of short trips at comparable rates. Most battery-costly tier - continuous GPS can drop phone battery life from ~284h to ~12h.",
  },
  {
    key: "standard_mobility",
    value: 180,
    label: "Standard mobility-pattern capture",
    detail:
      "3 min - general-purpose default balancing battery life against location-change detection for most phenotyping studies.",
  },
  {
    key: "battery_conservative",
    value: 600,
    label: "Battery-conservative",
    detail:
      "10 min - for multi-week deployments; accepts larger location gaps in exchange for battery life, similar to the on/off duty-cycling used by research platforms like Beiwe [GPS-Beiwe].",
  },
];

// WiFi / Bluetooth scanning and network-traffic polling, in seconds.
const SCAN_PRESETS = [
  {
    key: "realtime_colocation",
    value: 15,
    label: "Real-time co-location / indoor positioning",
    detail:
      "15s - matches Android's own default WiFi scan cadence; needed when the scan is used as a live proximity or position signal.",
  },
  {
    key: "standard_proximity",
    value: 60,
    label: "Standard social-proximity detection",
    detail:
      "60s - sufficient since the exact second a proximity ends rarely matters for the research question [BLE-Prox]; AWARE's existing default.",
  },
  {
    key: "battery_conservative",
    value: 300,
    label: "Battery-conservative",
    detail:
      "5 min - studies found only ~12% battery-life reduction from scanning this often over several hours [BLE-Prox]; appropriate for long deployments.",
  },
];

// CPU load sampling, in seconds. Unlike the sensors above, there is no
// digital-phenotyping literature recommending a specific processor sampling
// rate - this is a general systems-monitoring judgment call, not a research
// citation, and is labeled as such.
const PROCESSOR_PRESETS = [
  {
    key: "diagnostic",
    value: 1,
    label: "Diagnostic / real-time load monitoring",
    detail:
      "1s - cheap to sample (a local read, no radio involved); catches short CPU spikes from app launches. No phenotyping-specific literature recommends a rate here; this is general systems-monitoring judgment.",
  },
  {
    key: "standard",
    value: 10,
    label: "Standard housekeeping",
    detail:
      "10s - AWARE's existing default; adequate for correlating device load with battery/usage patterns.",
  },
  {
    key: "minimal",
    value: 60,
    label: "Minimal footprint",
    detail: "60s - coarse device-health context only.",
  },
];

// --- Plugin frequency presets -----------------------------------------
// Same approach as the core sensors above: named use cases with stated
// tradeoffs, not an arbitrary speed scale. Where no phenotyping-specific
// literature exists for a plugin's ideal rate (OpenWeather, Fitbit/HealthKit/
// pedometer sync, BLE heart-rate interval, contacts sync), the detail text
// says so explicitly and reasons from general engineering constraints
// (upstream API refresh rate, rate limits, OS-level batching) instead.

// Ambient noise plugin: how often a listening window is triggered, in
// minutes. Conversation-detection research uses much shorter duty cycles
// than this AWARE setting's unit implies, so the fastest option here is
// framed relative to that research rather than matching it exactly.
const AMBIENT_NOISE_PRESETS = [
  {
    key: "frequent",
    value: 2,
    label: "Frequent conversation-sensing",
    detail:
      "Every 2 min - closer to the ~1.5 min listening-window duty cycle used in conversation-detection research [StudentLife]; more battery and audio-processing cost.",
  },
  {
    key: "standard",
    value: 5,
    label: "Standard social-context logging",
    detail:
      "Every 5 min - AWARE's existing default; balances social-context resolution with battery life.",
  },
  {
    key: "battery_conservative",
    value: 15,
    label: "Battery-conservative",
    detail:
      "Every 15 min - coarse presence-of-speech context only, appropriate for long multi-week deployments.",
  },
];

// OpenWeather plugin sync frequency, in minutes. No phenotyping-specific
// literature recommends a rate here - reasoning instead from how often the
// underlying weather-data source actually refreshes.
const WEATHER_PRESETS = [
  {
    key: "responsive",
    value: 15,
    label: "Responsive local-weather context",
    detail:
      "Every 15 min - catches same-day weather transitions (e.g. rain starting); close to the useful ceiling since most weather APIs' source data doesn't update faster than hourly.",
  },
  {
    key: "standard",
    value: 30,
    label: "Standard (AWARE default)",
    detail:
      "Every 30 min - balances API-call budget against reasonably current conditions.",
  },
  {
    key: "minimal",
    value: 60,
    label: "Minimal footprint",
    detail:
      "Every 60 min - matches the roughly hourly refresh rate of most weather-data providers; polling faster doesn't get fresher data from the source.",
  },
];

// Google Activity Recognition plugin, in seconds - maps to the API's own
// detectionIntervalMillis parameter.
const ACTIVITY_RECOGNITION_PRESETS = [
  {
    key: "responsive",
    value: 10,
    label: "Responsive activity-change detection",
    detail:
      "10s - reflects activity changes quickly; higher battery cost [ActivityRec].",
  },
  {
    key: "standard",
    value: 30,
    label: "Standard (Google's documented balance point)",
    detail:
      "30s - Google's own developer guidance cites this as a reasonable balance between detection quality and battery life [ActivityRec].",
  },
  {
    key: "battery_conservative",
    value: 60,
    label: "Battery-conservative",
    detail:
      "60s - fewer detections and further-reduced battery cost; acceptable when only coarse activity context is needed.",
  },
];

// Fitbit sync frequency, in minutes. No literature specifies an ideal sync
// interval - reasoning instead from Fitbit's API rate limit (150
// requests/hour) and common practice in Fitbit-based studies.
const FITBIT_PRESETS = [
  {
    key: "frequent",
    value: 15,
    label: "Near-real-time sync",
    detail:
      "Every 15 min - keeps derived sleep/heart-rate/step data closer to real time; consumes more of Fitbit's API rate-limit budget (150 requests/hour) sooner.",
  },
  {
    key: "standard",
    value: 60,
    label: "Standard daily-resolution sync (AWARE default)",
    detail:
      "Every 60 min - adequate for day-level behavioral analysis, consistent with common practice in Fitbit-based mental-health studies [Fitbit-MH]; comfortably within API rate limits.",
  },
  {
    key: "minimal",
    value: 240,
    label: "Minimal footprint",
    detail: "Every 4 hours - coarse daily-trend only, lowest API/battery cost.",
  },
];

// Contacts-list sync, in minutes. A participant's contact list changes
// rarely, so this only gets two meaningfully distinct options.
const CONTACTS_PRESETS = [
  {
    key: "standard",
    value: 30,
    label: "Standard (AWARE default)",
    detail:
      "Every 30 min - catches new contacts reasonably promptly without excessive polling of a list that rarely changes.",
  },
  {
    key: "minimal",
    value: 1440,
    label: "Minimal footprint",
    detail:
      "Once daily (1440 min) - contact lists change rarely for most participants, so daily sync captures nearly all the same information at a fraction of the polling cost.",
  },
];

// Google Fused Location plugin, in seconds. Serves the same phenotyping
// purpose as the core GPS/network location sensors (mobility inference), so
// it reuses that literature rather than inventing separate reasoning.
const FUSED_LOCATION_PRESETS = [
  {
    key: "trip_capture",
    value: 30,
    label: "Trip / transportation-mode capture",
    detail:
      "30s - common research interval for catching trip start/end [GPS-Beiwe]; even so, GPS-trace studies show a majority of short trips are still missed at comparable rates. Highest battery cost of these options.",
  },
  {
    key: "standard_mobility",
    value: 180,
    label: "Standard mobility-pattern capture",
    detail:
      "3 min - general-purpose default balancing battery life against location-change detection.",
  },
  {
    key: "battery_conservative",
    value: 600,
    label: "Battery-conservative",
    detail:
      "10 min - for multi-week deployments; accepts larger location gaps in exchange for battery life.",
  },
];

// Conversations plugin off-duty period (idle time between listening
// windows), in seconds - the actual duty-cycle interval from the
// conversation-detection literature.
const CONVERSATIONS_PRESETS = [
  {
    key: "frequent",
    value: 30,
    label: "Frequent conversation-sensing",
    detail:
      "30s idle between listening windows - closer to real-time conversation detection; higher battery and audio-processing cost.",
  },
  {
    key: "studentlife_style",
    value: 90,
    label: "StudentLife-style duty cycle",
    detail:
      "~90s idle between short listening windows mirrors the audio duty-cycling used in conversation-detection research [StudentLife].",
  },
  {
    key: "battery_conservative",
    value: 300,
    label: "Battery-conservative",
    detail:
      "5 min idle between windows - captures far fewer conversations but substantially reduces battery and audio-processing load.",
  },
];

// Apple HealthKit sync frequency, in minutes. No phenotyping-specific
// literature recommends a rate, and iOS itself batches HealthKit background
// delivery regardless of the requested interval.
const HEALTHKIT_PRESETS = [
  {
    key: "frequent",
    value: 15,
    label: "Near-real-time sync",
    detail:
      "Every 15 min - closer to real time, though iOS HealthKit background delivery is itself OS-batched, so faster requests don't always yield fresher data.",
  },
  {
    key: "standard",
    value: 30,
    label: "Standard (AWARE default)",
    detail:
      "Every 30 min - reasonable balance for day-level behavioral analysis.",
  },
  {
    key: "minimal",
    value: 240,
    label: "Minimal footprint",
    detail: "Every 4 hours - coarse daily-trend only.",
  },
];

// BLE heart-rate plugin measurement interval, in minutes - how often the
// sensor is woken up for a single reading, not continuous monitoring.
const BLE_HEARTRATE_PRESETS = [
  {
    key: "frequent",
    value: 1,
    label: "Frequent measurement (AWARE default)",
    detail:
      "Every 1 min - closer to continuous monitoring; better chance of catching short-duration heart-rate changes (e.g. acute stress). Highest battery cost of these options.",
  },
  {
    key: "standard",
    value: 5,
    label: "Standard periodic measurement",
    detail:
      "Every 5 min - typical balance point for periodic (non-continuous) BLE heart-rate monitoring; still resolves most meaningful heart-rate trends.",
  },
  {
    key: "minimal",
    value: 15,
    label: "Minimal footprint",
    detail: "Every 15 min - coarse heart-rate-trend only, lowest battery cost.",
  },
];

// iOS pedometer sync frequency, in minutes. Step/distance counts are derived
// continuously on-device by iOS regardless of this setting - it only
// controls how often that data is synced to the study server.
const PEDOMETER_PRESETS = [
  {
    key: "frequent",
    value: 15,
    label: "Near-real-time sync",
    detail: "Every 15 min - keeps step/distance data closer to real time.",
  },
  {
    key: "standard",
    value: 30,
    label: "Standard (AWARE default)",
    detail: "Every 30 min - adequate for day-level step/activity analysis.",
  },
  {
    key: "minimal",
    value: 240,
    label: "Minimal footprint",
    detail: "Every 4 hours - coarse daily-trend only.",
  },
];

const FUSED_LOCATION_ACCURACY_OPTIONS = [
  { value: 100, label: "Max Precise Accuracy" },
  { value: 101, label: "Location Accuracy Nearest 10 Meters" },
  { value: 102, label: "Location Accuracy 100 Meters" },
  { value: 104, label: "Location Accuracy Kilometer" },
  { value: 105, label: "Location Accuracy 3 Kilometers" },
];

function normalizeFusedLocationAccuracy(value) {
  const numeric = Number(value);
  return FUSED_LOCATION_ACCURACY_OPTIONS.some(
    (option) => option.value === numeric
  )
    ? numeric
    : 102;
}

function AndroidOnlyNote() {
  return <p className="explanation">Android only feature.</p>;
}

export default function SensorData() {
  const navigateTo = useNavigate();
  const [sensorData, setsensorData] = useRecoilState(sensorDataState);

  const updateSensorData = (fieldName, value) => {
    setsensorData({
      ...sensorData,
      [fieldName]: value,
    });
  };

  // software sensor states
  const [applicationSensor, setapplicationSensor] = useRecoilState(
    applicationSensorState
  );

  const updateApplicationSensorData = (fieldName, value) => {
    setapplicationSensor({
      ...applicationSensor,
      [fieldName]: value,
    });
  };

  const [screenData, setscreenData] = useRecoilState(screenSensorState);

  const [communicationData, setcommunicationData] = useRecoilState(
    communicationSensorState
  );

  const [accelerometerData, setaccelerometerData] =
    useRecoilState(accelerometerState);

  const [gravityData, setgravityData] = useRecoilState(gravityState);

  const [timezoneData, setTimezoneData] = useRecoilState(timezoneState);

  const [barometerData, setbarometerData] = useRecoilState(barometerState);

  const [gyroscopeData, setgyroscopeData] = useRecoilState(gyroscopeState);

  const [lightData, setlightData] = useRecoilState(lightState);

  const [linearAccelerometerData, setLinearAccelerometerData] = useRecoilState(
    linearAccelerometerState
  );

  const [locationsData, setLocationsData] = useRecoilState(locationsState);

  const [magnetometerData, setmagnetometerData] =
    useRecoilState(magnetometerState);

  const [bluetoothData, setBluetoothData] = useRecoilState(bluetoothState);

  const [networkData, setNetworkData] = useRecoilState(networkState);

  const [processorData, setProcessorData] = useRecoilState(processorState);

  const [rotationData, setRotationData] = useRecoilState(rotationState);

  const [temperatureData, setTemperatureData] =
    useRecoilState(temperatureState);

  const [proximityData, setProximityData] = useRecoilState(proximityState);

  const [wifiData, setWifiData] = useRecoilState(wifiState);

  const [screenshotData, setScreenshotData] = useRecoilState(
    screenshotSensorState
  );

  const [noteData, setNoteData] = useRecoilState(noteState);

  const [pluginData, setPluginData] = useRecoilState(pluginSensorState);

  const updatePluginData = (fieldName, value) => {
    setPluginData({
      ...pluginData,
      [fieldName]: value,
    });
  };

  // eslint-disable-next-line react/no-unstable-nested-components
  function TextReader() {
    return (
      <div>
        <p className="field_name" mb={10}>
          Include or exclude specific packages to track *
        </p>
        <Grid marginTop={2}>
          <RadioGroup
            aria-labelledby="package_specification"
            name="package_specification"
            value={applicationSensor.package_specification || "2"}
            row
          >
            <FormControlLabel
              value="0"
              control={<Radio />}
              label="Inclusive packages"
              onClick={(_, checked) => {
                updateApplicationSensorData("package_specification", "0");
              }}
            />
            <FormControlLabel
              value="1"
              control={<Radio />}
              label="Exclusive packages"
              onClick={(_, checked) => {
                updateApplicationSensorData("package_specification", "1");
              }}
            />
            <FormControlLabel
              value="2"
              control={<Radio />}
              label="Default track all packages"
              onClick={(_, checked) => {
                updateApplicationSensorData("package_specification", "2");
              }}
            />
          </RadioGroup>
        </Grid>

        <Field
          fieldName="Package names"
          recoilState={applicationSensorState}
          field="package_names"
          inputLabel="Package names from the Google Play Store"
        />

        <Grid>
          <p className="explanation">
            You can leave the field blank if 'Default track all packages' is
            selected. Please list the package names, separated by a comma or
            space.
            <br />
            Example 1: com.aware.phone com.twitter.android
            <br />
            Example 2: com.aware.phone,com.twitter.android
            <br />
            Example 3: com.aware.phone, com.twitter.android
          </p>
        </Grid>
      </div>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorApplicationSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <SensorComponent
            sensorName="Notifications"
            sensorDescription="Activate or deactivate application notifications sensor."
            stateField={applicationSensor.notifications}
            field="notifications"
            modeState="application"
          />

          <SensorComponent
            sensorName="Crashes"
            sensorDescription="Activate or deactivate application crashes sensor."
            stateField={applicationSensor.crashes}
            field="crashes"
            modeState="application"
          />

          <FrequencyField
            id="frequency_applications"
            title="Frequency applications"
            inputLabel="seconds waiting for checking updates on background applications"
            defaultNum={30}
            description="How frequently to check updates on background applications and services statuses (default 30 seconds)"
            field="frequency_applications"
            studyField={applicationSensor.frequency_applications}
            modeState="application"
          />

          <SensorComponent
            sensorName="Keyboard sensor"
            sensorDescription="Log keyboard input."
            stateField={applicationSensor.keyboard}
            field="keyboard"
            modeState="application"
          />

          <SensorComponent
            sensorName="Mask keyboard"
            sensorDescription="Swaps all alphanumeric characters by A, a, and 1"
            stateField={applicationSensor.mask_keyboard}
            field="mask_keyboard"
            modeState="application"
          />

          <SensorComponent
            sensorName="Mask notification content"
            sensorDescription="Convert the notification messages into a irreversible code by applying a hash function"
            stateField={applicationSensor.mask_notification}
            field="mask_notification"
            modeState="application"
          />

          <SensorComponent
            sensorName="Mask touch text"
            sensorDescription="Swaps all alphanumeric characters by A, a, and 1"
            stateField={applicationSensor.mask_touch_text}
            field="mask_touch_text"
            modeState="application"
          />

          <SensorComponent
            sensorName="Text tracker"
            sensorDescription="Log text displayed on the screen. By default, all information except password fields will be recorded."
            stateField={applicationSensor.status_screentext}
            field="status_screentext"
            modeState="application"
          />

          {applicationSensor.status_screentext ? TextReader() : <div />}
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorCommunicationSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "12px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android only
          </p>
          <SensorComponent
            sensorName="Communication events"
            sensorDescription="Activate or deactivate high-level context of users’ communication usage."
            stateField={communicationData.events}
            field="events"
            modeState="communication"
          />

          <SensorComponent
            sensorName="Status messages sensor"
            sensorDescription="Activate or deactivate messages sensor."
            stateField={communicationData.messages}
            field="messages"
            modeState="communication"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorTimezoneSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_timezone"
            title="Frequency timezone"
            inputLabel="seconds checking for timezone change"
            defaultNum={200000}
            description="Frequency in seconds to check for changes in timezone."
            field="frequency_timezone"
            studyField={timezoneData.frequency_timezone}
            modeState="timezone"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorAccelerometerSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_sample_accelerometer"
            title="Sampling frequency (in microsec.)"
            inputLabel="frequency in microseconds"
            defaultNum={50000}
            description="Pick the option that matches what you're trying to detect - faster rates capture more detail but cost more battery and storage. Fused with gravity/gyroscope/linear-accelerometer/rotation, so those share this same table."
            field="frequency_sample_accelerometer"
            studyField={accelerometerData.frequency_sample_accelerometer}
            modeState="accelerometer"
            presets={MOTION_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold accelerometer"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={accelerometerData.threshold}
            allowZero
            modeState="accelerometer"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency accelerometer enforce"
            sensorDescription="Enforce sampling rate"
            stateField={accelerometerData.enforce}
            field="enforce"
            modeState="accelerometer"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorBarometerSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_sample_barometer"
            title="Sampling frequency (in microsec.)"
            inputLabel="frequency in microseconds"
            defaultNum={1000000}
            description="Barometric pressure mainly matters fused with accelerometer/gyroscope for floor-change detection; standalone, it changes slowly enough that fast sampling is pure oversampling."
            field="frequency_sample_barometer"
            studyField={barometerData.frequency_sample_barometer}
            modeState="barometer"
            presets={BAROMETER_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold barometer"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={barometerData.threshold}
            allowZero
            modeState="barometer"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency barometer enforce"
            sensorDescription="Enforce the frequency"
            stateField={barometerData.enforce}
            field="enforce"
            modeState="barometer"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorBluetoothSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_bluetooth"
            title="Frequency bluetooth"
            inputLabel="frequency in seconds"
            defaultNum={60}
            description="Bluetooth scans are typically used for social/co-location proximity - the exact second a proximity ends rarely matters, so faster scanning mostly just costs battery."
            field="frequency_bluetooth"
            studyField={bluetoothData.frequency_bluetooth}
            modeState="bluetooth"
            presets={SCAN_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorGravitySubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_gravity"
            title="Frequency gravity"
            inputLabel="frequency in microseconds"
            defaultNum={50000}
            description="Kept consistent with the accelerometer, since gravity is typically used to separate the gravity component out of raw accelerometer readings."
            field="frequency_gravity"
            studyField={gravityData.frequency_gravity}
            modeState="gravity"
            presets={MOTION_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold gravity"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={gravityData.threshold}
            allowZero
            modeState="gravity"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency gravity enforce"
            sensorDescription="Enforce the frequency"
            stateField={gravityData.enforce}
            field="enforce"
            modeState="gravity"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorGyroscopeSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_gyroscope"
            title="Frequency gyroscope"
            inputLabel="frequency in microseconds"
            defaultNum={50000}
            description="Kept consistent with the accelerometer, since gyroscope + accelerometer are commonly fused for orientation/attitude estimation."
            field="frequency_gyroscope"
            studyField={gyroscopeData.frequency_gyroscope}
            modeState="gyroscope"
            presets={MOTION_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold gyroscope"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={gyroscopeData.threshold}
            allowZero
            modeState="gyroscope"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency gyroscope enforce"
            sensorDescription="Enforce the frequency"
            stateField={gyroscopeData.enforce}
            field="enforce"
            modeState="gyroscope"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorLightSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_light"
            title="Frequency light"
            inputLabel="frequency in microseconds"
            defaultNum={1000000}
            description="Ambient light changes slowly relative to motion sensors - pick the option matching what environmental transitions you actually need to capture."
            field="frequency_light"
            studyField={lightData.frequency_light}
            modeState="light"
            presets={LIGHT_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold light"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={lightData.threshold}
            allowZero
            modeState="light"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency light enforce"
            sensorDescription="Enforce the frequency"
            stateField={lightData.enforce}
            field="enforce"
            modeState="light"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorLinearAccelerometerSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_linear_accelerometer"
            title="Frequency linear accelerometer"
            inputLabel="frequency in microseconds"
            defaultNum={50000}
            description="Kept consistent with the accelerometer, since linear acceleration is the gravity-removed version of the same raw signal."
            field="frequency_linear_accelerometer"
            studyField={linearAccelerometerData.frequency_linear_accelerometer}
            modeState="linearAccelerometer"
            presets={MOTION_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold linear accelerometer"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={linearAccelerometerData.threshold}
            allowZero
            modeState="linearAccelerometer"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency linear accelerometer enforce"
            sensorDescription="Enforce the frequency"
            stateField={linearAccelerometerData.enforce}
            field="enforce"
            modeState="linearAccelerometer"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorLocationsSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "8px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android &amp; iPhone
          </p>
          <SensorComponent
            sensorName="Location (GPS)"
            sensorDescription="Activate or deactivate GPS locations."
            stateField={locationsData.gps}
            field="gps"
            modeState="locations"
          />

          <FrequencyField
            id="frequency_gps"
            title="Frequency GPS"
            inputLabel="frequency in seconds"
            defaultNum={180}
            description="GPS is the single most battery-expensive sensor on the phone. Setting to 0 (zero) will keep GPS tracking always on - not recommended outside short, high-resolution trip studies."
            field="frequency_gps"
            studyField={locationsData.frequency_gps}
            modeState="locations"
            presets={LOCATION_PRESETS}
          />

          <FrequencyField
            id="min_gps_freq"
            title="Min GPS accuracy"
            inputLabel="minimum accuracy in meters"
            defaultNum={150}
            description="The minimum acceptable accuracy of GPS location, in meters. By default, 150 meters."
            field="min_gps_freq"
            studyField={locationsData.min_gps_freq}
            modeState="locations"
          />

          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "12px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android only
          </p>
          <SensorComponent
            sensorName="Location (Network)"
            sensorDescription="Activate or deactivate Network locations."
            stateField={locationsData.network}
            field="network"
            modeState="locations"
          />

          <FrequencyField
            id="frequency_network"
            title="Frequency network"
            inputLabel="frequency in seconds"
            defaultNum={180}
            description="Harmonized to the same options as GPS so both location sources stay consistent with each other. Setting to 0 (zero) will keep network location tracking always on."
            field="frequency_network"
            studyField={locationsData.frequency_network}
            modeState="locations"
            presets={LOCATION_PRESETS}
          />

          <FrequencyField
            id="min_network_freq"
            title="Min location network accuracy"
            inputLabel="minimum accuracy in meters"
            defaultNum={1500}
            description="The minimum acceptable accuracy of network location, in meters. By default, 1500 meters."
            field="min_network_freq"
            studyField={locationsData.min_network_freq}
            modeState="locations"
          />

          <FrequencyField
            id="expiration"
            title="Location expiration time"
            inputLabel="expiration time in seconds"
            defaultNum={300}
            description="The amount of elapsed time, in seconds, until the location is considered outdated. By default, 300 seconds."
            field="expiration"
            studyField={locationsData.expiration}
            modeState="locations"
          />

          <SensorComponent
            sensorName="Passive location"
            sensorDescription="Don't fetch locations, but use locations if other apps request them."
            stateField={locationsData.passive}
            field="passive"
            modeState="locations"
          />

          <SensorComponent
            sensorName="Save all locations"
            sensorDescription="Don't use heuristics to only record best locations"
            stateField={locationsData.save_all}
            field="save_all"
            modeState="locations"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorMagnetometerSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_magnetometer"
            title="Frequency magnetometer"
            inputLabel="frequency in microseconds"
            defaultNum={200000}
            description="Magnetometer readings change more slowly than raw motion and are mainly useful fused with gyroscope/accelerometer for heading estimation."
            field="frequency_magnetometer"
            studyField={magnetometerData.frequency_magnetometer}
            modeState="magnetometer"
            presets={MAGNETOMETER_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold magnetometer"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={magnetometerData.threshold}
            allowZero
            modeState="magnetometer"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency magnetometer enforce"
            sensorDescription="Enforce the frequency"
            stateField={magnetometerData.enforce}
            field="enforce"
            modeState="magnetometer"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorNetworkSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "8px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android &amp; iPhone
          </p>
          <SensorComponent
            sensorName="Network events"
            sensorDescription="Activate or deactivate sensor."
            stateField={networkData.events}
            field="events"
            modeState="network"
          />

          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "12px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android only
          </p>
          <SensorComponent
            sensorName="Network traffic"
            sensorDescription="Activate or deactivate sensor."
            stateField={networkData.traffic}
            field="traffic"
            modeState="network"
          />

          <FrequencyField
            id="frequency_network_traffic"
            title="Network traffic frequency"
            inputLabel="frequency in seconds"
            defaultNum={60}
            description="Uses the same options as WiFi/Bluetooth scanning to stay consistent with the other polling sensors."
            field="frequency_network_traffic"
            studyField={networkData.frequency_network_traffic}
            modeState="network"
            presets={SCAN_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorProcessorSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_processor"
            title="Frequency processor"
            inputLabel="frequency in seconds"
            defaultNum={10}
            description="Frequency in seconds to update the processor load. Android receives this value in seconds; iPhone config receives the same interval converted to microseconds. Note: unlike the other sensors here, there's no phenotyping-specific literature behind these options - see the option descriptions."
            field="frequency_processor"
            studyField={processorData.frequency_processor}
            modeState="processor"
            presets={PROCESSOR_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorProximitySubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "8px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android only
          </p>
          <FrequencyField
            id="frequency_proximity"
            title="Frequency proximity"
            inputLabel="frequency in microseconds"
            defaultNum={1000000}
            description="Proximity is fundamentally a near/far event sensor rather than a continuous stream, so only two meaningfully distinct rates make sense here."
            field="frequency_proximity"
            studyField={proximityData.frequency_proximity}
            modeState="proximity"
            presets={PROXIMITY_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold proximity"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={proximityData.threshold}
            allowZero
            modeState="proximity"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency proximity enforce"
            sensorDescription="Enforce the frequency"
            stateField={proximityData.enforce}
            field="enforce"
            modeState="proximity"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorRotationSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_rotation"
            title="Frequency rotation"
            inputLabel="frequency in microseconds"
            defaultNum={50000}
            description="Kept consistent with the accelerometer, since the rotation vector is a fused (accelerometer + gyroscope + magnetometer) orientation estimate."
            field="frequency_rotation"
            studyField={rotationData.frequency_rotation}
            modeState="rotation"
            presets={MOTION_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold rotation"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={rotationData.threshold}
            allowZero
            modeState="rotation"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency rotation enforce"
            sensorDescription="Enforce the frequency"
            stateField={rotationData.enforce}
            field="enforce"
            modeState="rotation"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorTemperatureSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_temperature"
            title="Frequency temperature"
            inputLabel="frequency in microseconds"
            defaultNum={10000000}
            description="Ambient temperature (where the hardware exists at all) tracks slow-moving weather/environment - there's no phenotyping case for sub-10-second sampling."
            field="frequency_temperature"
            studyField={temperatureData.frequency_temperature}
            modeState="temperature"
            presets={TEMPERATURE_PRESETS}
          />

          <FrequencyField
            id="threshold"
            title="Threshold temperature"
            inputLabel="threshold"
            defaultNum={0}
            description="E.g., log only if [x,y,z] >= 0.01. 0 = disabled"
            field="threshold"
            studyField={temperatureData.threshold}
            allowZero
            modeState="temperature"
          />

          <AndroidOnlyNote />
          <SensorComponent
            sensorName="Frequency temperature enforce"
            sensorDescription="Enforce the frequency"
            stateField={temperatureData.enforce}
            field="enforce"
            modeState="temperature"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorWifiSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_wifi"
            title="Frequency Wi-Fi (seconds)"
            inputLabel="frequency in seconds"
            defaultNum={60}
            description="WiFi scans are typically used for co-location/indoor-positioning signals or general context - pick based on how time-sensitive that signal needs to be."
            field="frequency_wifi"
            studyField={wifiData.frequency_wifi}
            modeState="wifi"
            presets={SCAN_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorScreenSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <p
            style={{
              fontSize: "0.7rem",
              fontWeight: 700,
              color: "#666",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              margin: "8px 0 2px",
              borderBottom: "1px solid #e0e0e0",
              paddingBottom: 2,
            }}
          >
            Android only
          </p>
          <SensorComponent
            sensorName="Touch"
            sensorDescription="Logs clicks, long-clicks and scroll up/down events."
            stateField={screenData.sensor_touch}
            field="sensor_touch"
            modeState="screen"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorScreenshotSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="capture_time_interval"
            title="Capture Time Interval"
            inputLabel="Time interval between screenshots (seconds)"
            defaultNum={5}
            description="Time interval between each screenshot capture in seconds."
            field="capture_time_interval"
            studyField={screenshotData.capture_time_interval}
            modeState="screenshot"
          />
          <FrequencyField
            id="compress_rate"
            title="Compression Rate"
            inputLabel="Compression rate for screenshots"
            defaultNum={20}
            description="Compression rate for the screenshots (1-100). 1 meaning compress for small size, 100 meaning compress for max quality. On default, a compression rate of 20 offers a good balance between quality and storage cost (average 60kb/per screenshot on testing device like Pixel 8)."
            field="compress_rate"
            studyField={screenshotData.compress_rate}
            modeState="screenshot"
          />
          <SensorComponent
            sensorName="Local Storage"
            sensorDescription="Choose whether to save screenshot images locally in addition to syncing with the remote database. Screenshots are always synced to the remote database. If local storage is enabled, screenshots will also be saved in the folder located at /download/aware/screenshot/ on participant's device."
            stateField={screenshotData.status_screenshot_local_storage}
            field="status_screenshot_local_storage"
            modeState="screenshot"
          />

          <div>
            <p className="field_name" mb={10}>
              Include or exclude specific package to capture *
            </p>
            <Grid marginTop={2}>
              <RadioGroup
                aria-labelledby="screenshot_package_specification"
                name="screenshot_package_specification"
                value={applicationSensor.screenshot_package_specification}
                row
              >
                <FormControlLabel
                  value="0"
                  control={<Radio />}
                  label="Inclusive packages"
                  onClick={(_, checked) => {
                    updateApplicationSensorData(
                      "screenshot_package_specification",
                      "0"
                    );
                  }}
                />
                <FormControlLabel
                  value="1"
                  control={<Radio />}
                  label="Exclusive packages"
                  onClick={(_, checked) => {
                    updateApplicationSensorData(
                      "screenshot_package_specification",
                      "1"
                    );
                  }}
                />
                <FormControlLabel
                  value="2"
                  control={<Radio />}
                  label="Default track all packages"
                  onClick={(_, checked) => {
                    updateApplicationSensorData(
                      "screenshot_package_specification",
                      "2"
                    );
                  }}
                />
              </RadioGroup>
            </Grid>

            <Field
              fieldName="Package names"
              recoilState={applicationSensorState}
              field="screenshot_package_names"
              inputLabel="Package names from google store"
            />

            <Grid>
              <p className="explanation">
                You may leave the field blank if default is selected. Please
                list the package names separated by comma or space.
                <br />
                Example 1: com.aware.phone com.twitter.android
                <br />
                Example 2: com.aware.phone,com.twitter.android
                <br />
                Example 3: com.aware.phone, com.twitter.android
              </p>
            </Grid>
          </div>
        </Grid>
      </Grid>
    );
  }
  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginAmbientNoiseSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_plugin_ambient_noise"
            title="Sampling Frequency"
            inputLabel="How frequently to sample the microphone (minutes)"
            defaultNum={5}
            description="How often a listening window is triggered - faster catches more conversations but costs more battery and raises more audio-processing/privacy exposure."
            field="frequency_plugin_ambient_noise"
            studyField={pluginData.frequency_plugin_ambient_noise}
            modeState="plugin"
            presets={AMBIENT_NOISE_PRESETS}
          />
          <FrequencyField
            id="plugin_ambient_noise_sample_size"
            title="Sample Size"
            inputLabel="Duration of each sample (seconds)"
            defaultNum={30}
            description="Duration of each ambient noise sample in seconds."
            field="plugin_ambient_noise_sample_size"
            studyField={pluginData.plugin_ambient_noise_sample_size}
            modeState="plugin"
          />
          <FrequencyField
            id="plugin_ambient_noise_silence_threshold"
            title="Silence Threshold"
            inputLabel="Silence threshold (dB)"
            defaultNum={50}
            description="Threshold for considering ambient noise as silence (in dB)."
            field="plugin_ambient_noise_silence_threshold"
            studyField={pluginData.plugin_ambient_noise_silence_threshold}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function SensorMqttSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <div className="sensor_vertical_layout">
            <Grid>
              <p className="field_name" mb={10}>
                Broker address
              </p>
            </Grid>
            <Grid marginTop={2}>
              <TextField
                id="mqtt_server"
                placeholder="mqtt.example.com"
                value={sensorData.mqtt_server || ""}
                type="text"
                style={{ width: "100%" }}
                onChange={(event) => {
                  updateSensorData("mqtt_server", event.target.value);
                }}
              />
              <p className="explanation">
                Hostname or IP address of the MQTT broker the client should
                connect to.
              </p>
            </Grid>
          </div>

          <FrequencyField
            id="mqtt_port"
            title="Broker port"
            inputLabel="MQTT broker port"
            defaultNum={1883}
            description="Port the MQTT broker listens on (default 1883, or 8883 for TLS)."
            field="mqtt_port"
            studyField={sensorData.mqtt_port}
            modeState="sensor"
          />

          <div className="sensor_vertical_layout">
            <Grid>
              <p className="field_name" mb={10}>
                Username
              </p>
            </Grid>
            <Grid marginTop={2}>
              <TextField
                id="mqtt_username"
                placeholder="Optional"
                value={sensorData.mqtt_username || ""}
                type="text"
                style={{ width: "100%" }}
                onChange={(event) => {
                  updateSensorData("mqtt_username", event.target.value);
                }}
              />
              <p className="explanation">
                Username for authenticating with the broker, if required.
              </p>
            </Grid>
          </div>

          <PasswordField
            fieldName="Password"
            recoilState={sensorDataState}
            field="mqtt_password"
            inputLabel="Optional"
            description="Password for authenticating with the broker, if required."
          />

          <FrequencyField
            id="mqtt_keep_alive"
            title="Keep alive"
            inputLabel="Keep-alive interval (seconds)"
            defaultNum={600}
            description="How often the client pings the broker to keep the connection alive (seconds)."
            field="mqtt_keep_alive"
            studyField={sensorData.mqtt_keep_alive}
            modeState="sensor"
          />

          <div>
            <Grid>
              <p className="field_name" mb={10}>
                QoS level
              </p>
            </Grid>
            <Grid marginTop={2}>
              <RadioGroup
                aria-labelledby="mqtt_qos"
                name="mqtt_qos"
                value={
                  sensorData.mqtt_qos !== undefined ? sensorData.mqtt_qos : 2
                }
                row
              >
                <FormControlLabel
                  value={0}
                  control={<Radio />}
                  label="0 - At most once"
                  onClick={() => updateSensorData("mqtt_qos", 0)}
                />
                <FormControlLabel
                  value={1}
                  control={<Radio />}
                  label="1 - At least once"
                  onClick={() => updateSensorData("mqtt_qos", 1)}
                />
                <FormControlLabel
                  value={2}
                  control={<Radio />}
                  label="2 - Exactly once"
                  onClick={() => updateSensorData("mqtt_qos", 2)}
                />
              </RadioGroup>
              <p className="schedule-description">
                Quality of service level for published/subscribed MQTT messages.
              </p>
            </Grid>
          </div>
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginOpenWeatherSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="plugin_openweather_frequency"
            title="Update Frequency"
            inputLabel="How often to fetch weather data (minutes)"
            defaultNum={30}
            description="No phenotyping literature dictates this rate - it's bounded mostly by how often the underlying weather-data source actually refreshes."
            field="plugin_openweather_frequency"
            studyField={pluginData.plugin_openweather_frequency}
            modeState="plugin"
            presets={WEATHER_PRESETS}
          />

          <PluginAPIField
            id="plugin_openweather_api_key"
            title="API Key"
            inputLabel="OpenWeather API Key"
            description="API key for OpenWeatherMap. You can get it by registering at https://home.openweathermap.org/users/sign_up"
            field="plugin_openweather_api_key"
            studyField={pluginData.plugin_openweather_api_key}
            modeState="plugin"
          />

          <Grid>
            <p className="field_name" mb={10}>
              Measurement unit
            </p>
          </Grid>
          <RadioGroup
            aria-labelledby="Measurement units"
            name="measurement units"
            value={pluginData.plugin_openweather_measurement_units || "metric"}
            row
          >
            <FormControlLabel
              value="metric"
              control={<Radio />}
              label="Metric"
              onClick={(_, checked) => {
                updatePluginData(
                  "plugin_openweather_measurement_units",
                  "metric"
                );
              }}
            />
            <FormControlLabel
              value="imperial"
              control={<Radio />}
              label="Imperial"
              onClick={(_, checked) => {
                updatePluginData(
                  "plugin_openweather_measurement_units",
                  "imperial"
                );
              }}
            />
          </RadioGroup>
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginActivityRecognitionSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_plugin_google_activity_recognition"
            title="Update Frequency"
            inputLabel="How often to detect activity (seconds)"
            defaultNum={30}
            description="Maps directly to Google's own detectionIntervalMillis parameter."
            field="frequency_plugin_google_activity_recognition"
            studyField={pluginData.frequency_plugin_google_activity_recognition}
            modeState="plugin"
            presets={ACTIVITY_RECOGNITION_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginFitbitSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="plugin_fitbit_frequency"
            title="Sync Frequency"
            inputLabel="How often to sync Fitbit data (minutes)"
            defaultNum={60}
            description="No literature specifies an ideal sync interval - bounded mainly by Fitbit's API rate limit (150 requests/hour) and common practice in Fitbit-based studies."
            field="plugin_fitbit_frequency"
            studyField={pluginData.plugin_fitbit_frequency}
            modeState="plugin"
            presets={FITBIT_PRESETS}
          />

          <PluginAPIField
            id="api_key_plugin_fitbit"
            title="API Key"
            inputLabel="Fitbit OAuth Client ID"
            description="Fitbit OAuth 2.0 Client ID from dev.fitbit.com"
            field="api_key_plugin_fitbit"
            studyField={pluginData.api_key_plugin_fitbit}
            modeState="plugin"
          />

          <PluginAPIField
            id="api_secret_plugin_fitbit"
            title="API Secret"
            inputLabel="Fitbit OAuth Client Secret"
            description="Fitbit OAuth 2.0 Client Secret from dev.fitbit.com"
            field="api_secret_plugin_fitbit"
            studyField={pluginData.api_secret_plugin_fitbit}
            modeState="plugin"
          />

          <Grid>
            <p className="field_name" mb={10}>
              Measurement unit
            </p>
          </Grid>
          <RadioGroup
            aria-labelledby="Fitbit units"
            name="fitbit units"
            value={pluginData.units_plugin_fitbit || "metric"}
            row
          >
            <FormControlLabel
              value="metric"
              control={<Radio />}
              label="Metric"
              onClick={() => updatePluginData("units_plugin_fitbit", "metric")}
            />
            <FormControlLabel
              value="imperial"
              control={<Radio />}
              label="Imperial"
              onClick={() =>
                updatePluginData("units_plugin_fitbit", "imperial")
              }
            />
          </RadioGroup>

          <Grid>
            <p className="field_name" mb={10}>
              Steps/sleep granularity (minutes)
            </p>
          </Grid>
          <RadioGroup
            aria-labelledby="Fitbit granularity"
            name="fitbit granularity"
            value={String(pluginData.fitbit_granularity ?? 15)}
            row
          >
            {[1, 15, 30, 60].map((v) => (
              <FormControlLabel
                key={v}
                value={String(v)}
                control={<Radio />}
                label={`${v} min`}
                onClick={() => updatePluginData("fitbit_granularity", v)}
              />
            ))}
          </RadioGroup>

          <Grid>
            <p className="field_name" mb={10}>
              Heart-rate granularity
            </p>
          </Grid>
          <RadioGroup
            aria-labelledby="Fitbit HR granularity"
            name="fitbit hr granularity"
            value={String(pluginData.fitbit_hr_granularity ?? 1)}
            row
          >
            <FormControlLabel
              value="1"
              control={<Radio />}
              label="1 second"
              onClick={() => updatePluginData("fitbit_hr_granularity", 1)}
            />
            <FormControlLabel
              value="60"
              control={<Radio />}
              label="1 minute"
              onClick={() => updatePluginData("fitbit_hr_granularity", 60)}
            />
          </RadioGroup>
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginContactsListSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_plugin_contacts"
            title="Sync Frequency"
            inputLabel="How often to sync contacts (minutes)"
            defaultNum={30}
            description="A participant's contact list changes rarely, so only two meaningfully distinct rates make sense here."
            field="frequency_plugin_contacts"
            studyField={pluginData.frequency_plugin_contacts}
            modeState="plugin"
            presets={CONTACTS_PRESETS}
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginGoogleFusedLocationSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_google_fused_location"
            title="Update Frequency"
            inputLabel="How often to request location (seconds)"
            defaultNum={180}
            description="Serves the same mobility-inference purpose as the core GPS/network location sensors, so it reuses that same literature-backed set of options."
            field="frequency_google_fused_location"
            studyField={pluginData.frequency_google_fused_location}
            modeState="plugin"
            presets={FUSED_LOCATION_PRESETS}
          />
          <FrequencyField
            id="max_frequency_google_fused_location"
            title="Max Update Frequency"
            inputLabel="Fastest location update interval (seconds)"
            defaultNum={60}
            description="Maximum frequency at which the app can receive location updates."
            field="max_frequency_google_fused_location"
            studyField={pluginData.max_frequency_google_fused_location}
            modeState="plugin"
          />
          <FrequencyField
            id="fallback_location_timeout"
            title="Fallback Timeout"
            inputLabel="Fallback timeout (seconds)"
            defaultNum={20}
            description="Timeout before switching to a lower-accuracy provider."
            field="fallback_location_timeout"
            studyField={pluginData.fallback_location_timeout}
            modeState="plugin"
          />
          <Grid>
            <p className="field_name" mb={10}>
              Location Accuracy
            </p>
          </Grid>
          <RadioGroup
            aria-labelledby="Location Accuracy"
            name="location accuracy"
            value={String(
              normalizeFusedLocationAccuracy(
                pluginData.accuracy_google_fused_location
              )
            )}
          >
            {FUSED_LOCATION_ACCURACY_OPTIONS.map((option) => (
              <FormControlLabel
                key={option.value}
                value={String(option.value)}
                control={<Radio />}
                label={option.label}
                onClick={() =>
                  updatePluginData(
                    "accuracy_google_fused_location",
                    option.value
                  )
                }
              />
            ))}
          </RadioGroup>
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginConversationsSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="plugin_conversations_delay"
            title="Start Delay"
            inputLabel="Delay before recording starts (seconds)"
            defaultNum={5}
            description="Delay in seconds before the plugin begins audio detection."
            field="plugin_conversations_delay"
            studyField={pluginData.plugin_conversations_delay}
            modeState="plugin"
          />
          <FrequencyField
            id="plugin_conversations_off_duty"
            title="Off-duty Period"
            inputLabel="Off-duty period between samples (seconds)"
            defaultNum={90}
            description="This is the plugin's actual duty-cycle interval - shorter idle periods catch more conversations at higher battery/processing cost."
            field="plugin_conversations_off_duty"
            studyField={pluginData.plugin_conversations_off_duty}
            modeState="plugin"
            presets={CONVERSATIONS_PRESETS}
          />
          <FrequencyField
            id="plugin_conversations_length"
            title="Sample Length"
            inputLabel="Duration of each audio sample (seconds)"
            defaultNum={60}
            description="Duration in seconds of each audio detection window."
            field="plugin_conversations_length"
            studyField={pluginData.plugin_conversations_length}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginHealthKitSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_health_kit"
            title="Sync Frequency"
            inputLabel="How often to sync HealthKit data (minutes)"
            defaultNum={30}
            description="No phenotyping literature recommends a rate, and iOS itself batches HealthKit background delivery regardless of the requested interval."
            field="frequency_health_kit"
            studyField={pluginData.frequency_health_kit}
            modeState="plugin"
            presets={HEALTHKIT_PRESETS}
          />
          <FrequencyField
            id="preperiod_days_health_kit"
            title="Pre-period Days"
            inputLabel="Days of historical data to fetch on join"
            defaultNum={7}
            description="Number of days of historical HealthKit data to fetch when a participant joins."
            field="preperiod_days_health_kit"
            studyField={pluginData.preperiod_days_health_kit}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginBLEHeartRateSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="plugin_ble_heartrate_interval_min"
            title="Measurement Interval"
            inputLabel="How often to measure heart rate (minutes)"
            defaultNum={1}
            description="How frequently the BLE heart rate sensor is woken up for a single measurement (not continuous monitoring)."
            field="plugin_ble_heartrate_interval_min"
            studyField={pluginData.plugin_ble_heartrate_interval_min}
            modeState="plugin"
            presets={BLE_HEARTRATE_PRESETS}
          />
          <FrequencyField
            id="plugin_ble_heartrate_active_time_sec"
            title="Active Time"
            inputLabel="BLE sensor active duration (seconds)"
            defaultNum={30}
            description="How long the BLE sensor stays active to acquire each measurement."
            field="plugin_ble_heartrate_active_time_sec"
            studyField={pluginData.plugin_ble_heartrate_active_time_sec}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginIosPedometerSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <FrequencyField
            id="frequency_ios_pedometer"
            title="Sync Frequency"
            inputLabel="How often to sync pedometer data (minutes)"
            defaultNum={30}
            description="Step/distance counts are derived continuously on-device by iOS regardless of this setting - it only controls how often that data is synced to the study server."
            field="frequency_ios_pedometer"
            studyField={pluginData.frequency_ios_pedometer}
            modeState="plugin"
            presets={PEDOMETER_PRESETS}
          />
          <FrequencyField
            id="preperiod_days_ios_pedometer"
            title="Pre-period Days"
            inputLabel="Days of historical data to fetch on join"
            defaultNum={7}
            description="Number of days of historical pedometer data to fetch when a participant joins."
            field="preperiod_days_ios_pedometer"
            studyField={pluginData.preperiod_days_ios_pedometer}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  // eslint-disable-next-line react/no-unstable-nested-components
  function PluginPushNotificationSubContent() {
    return (
      <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
        <Grid width="10%" />
        <Grid width="70%">
          <PluginAPIField
            id="plugin_push_notification_server"
            title="Server URL"
            inputLabel="Push notification server endpoint URL"
            description="URL of the push notification server that delivers notifications to participants."
            field="plugin_push_notification_server"
            studyField={pluginData.plugin_push_notification_server}
            modeState="plugin"
          />
        </Grid>
      </Grid>
    );
  }

  return (
    <ThemeProvider theme={customisedTheme}>
      <div className="main_vertical_layout">
        <div className="border">
          <p className="title">Sensors data</p>
          <p className="explanation">
            Collect sensor data from the participants' phone during your study.
            Some sensors require specific permissions to be enabled on the
            phone. These are automatically requested when the study is joined.
            Keep in mind that the collection of multiple sensors at high
            frequency can decrease battery life of the phone. Sensors are
            grouped by platform availability.
          </p>
        </div>

        <div className="border">
          <p className="title">Configuration settings</p>
          <SensorComponent
            sensorName="Sync to server"
            sensorDescription="Upload collected data to the study webservice. Disable to keep data on-device only."
            stateField={
              sensorData.status_webservice !== undefined
                ? sensorData.status_webservice
                : true
            }
            field="status_webservice"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Wifi only"
            sensorDescription="Upload data only when connected to Wi-Fi."
            stateField={sensorData.wifi_only}
            field="wifi_only"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Charging only"
            sensorDescription="Upload only if charging."
            stateField={sensorData.charging_only}
            field="charging_only"
            modeState="sensor"
          />

          <FrequencyField
            id="offload_frequency"
            title="Offload frequency"
            inputLabel="sychronised frequency in minutes"
            defaultNum={30}
            description="How often the data is synchronised with the webservices (min)?"
            field="offload_frequency"
            studyField={sensorData.offload_frequency}
            modeState="sensor"
          />

          <div>
            <Grid>
              <p className="field_name" mb={10}>
                Clean data frequency on the participants' devices
              </p>
            </Grid>
            <Grid marginTop={2}>
              <RadioGroup
                aria-labelledby="clean_data_freq"
                name="clean_data_freq"
                value={sensorData.clean_data_freq || "0"}
                row
              >
                <FormControlLabel
                  value="0"
                  control={<Radio />}
                  label="Never"
                  onClick={(_, checked) => {
                    updateSensorData("clean_data_freq", "0");
                  }}
                />
                <FormControlLabel
                  value="2"
                  control={<Radio />}
                  label="Monthly"
                  onClick={(_, checked) => {
                    updateSensorData("clean_data_freq", "2");
                  }}
                />
                <FormControlLabel
                  value="1"
                  control={<Radio />}
                  label="Weekly"
                  onClick={(_, checked) => {
                    updateSensorData("clean_data_freq", "1");
                  }}
                />
                <FormControlLabel
                  value="3"
                  control={<Radio />}
                  label="Daily"
                  // checked={}
                  onClick={(_, checked) => {
                    updateSensorData("clean_data_freq", "3");
                  }}
                />
                <FormControlLabel
                  value="4"
                  control={<Radio />}
                  label="Always"
                  // checked={}
                  onClick={(_, checked) => {
                    updateSensorData("clean_data_freq", "4");
                  }}
                />
              </RadioGroup>
              <p className="schedule-description">
                How frequently to clean old data?
              </p>
            </Grid>
          </div>

          <SensorComponent
            sensorName="Silent"
            sensorDescription="Don't show sync notifications."
            stateField={sensorData.no_sync_notify}
            field="no_sync_notify"
            modeState="sensor"
          />

          <FrequencyField
            id="fallback_network"
            title="Fallback network"
            inputLabel="maximum number of trying over wifi"
            defaultNum={30}
            description="Fallback to 3G syncing after specified number of hours trying over WiFi."
            studyField={sensorData.fallback_network}
            field="fallback_network"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Remind to charge"
            sensorDescription="Remind to charge when 15% battery is left."
            stateField={sensorData.charge_reminder}
            field="charge_reminder"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Foreground priority"
            sensorDescription="Recommended to keep AWARE running non-stop."
            stateField={sensorData.foreground_priority}
            field="foreground_priority"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Debug flag"
            sensorDescription="Show debug messages in logcat."
            stateField={sensorData.debug_flag}
            field="debug_flag"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Slow database warnings"
            sensorDescription="Log a warning when a local database operation takes too long."
            stateField={sensorData.debug_db_slow}
            field="debug_db_slow"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Simple webservice payloads"
            sensorDescription="Upload data using the simplified webservice payload format."
            stateField={sensorData.webservice_simple}
            field="webservice_simple"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Remove data after upload"
            sensorDescription="Delete local sensor data once it has been successfully uploaded to the webservice."
            stateField={sensorData.webservice_remove_data}
            field="webservice_remove_data"
            modeState="sensor"
          />

          <FrequencyField
            id="config_update_freq"
            title="Config update frequency"
            inputLabel="minutes waiting for checking updates"
            defaultNum={60}
            description="How frequently to check for new study config (min)?"
            field="config_update_freq"
            studyField={sensorData.config_update_freq}
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Enable settings update"
            sensorDescription="Allow participants to modify the study config from the mobile."
            stateField={sensorData.setting_update}
            field="setting_update"
            modeState="sensor"
          />
        </div>

        <div className="border">
          <p className="title">Shared sensors</p>
          <SensorComponent
            sensorName="Battery"
            sensorDescription="Battery information and power related events (phone shutting down, rebooting)."
            stateField={sensorData.sensor_battery}
            field="sensor_battery"
            modeState="sensor"
          />
          <SensorComponent
            sensorName="Communication (Calls)"
            sensorDescription="Call events on iPhone and Android. Android-only communication events and text messages can be controlled below."
            stateField={sensorData.sensor_communication}
            field="sensor_communication"
            modeState="sensor"
          />

          {sensorData.sensor_communication ? (
            SensorCommunicationSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Screen"
            sensorDescription="Smartphone screen status; turning on, turning off, lock, and unlock."
            stateField={sensorData.sensor_screen}
            field="sensor_screen"
            modeState="sensor"
          />
          {sensorData.sensor_screen ? SensorScreenSubContent() : <div />}

          <SensorComponent
            sensorName="Timezone"
            sensorDescription="Logs user's current timezone."
            stateField={sensorData.sensor_timezone}
            field="sensor_timezone"
            modeState="sensor"
          />

          {sensorData.sensor_timezone ? SensorTimezoneSubContent() : <div />}

          <SensorComponent
            sensorName="Accelerometer"
            sensorDescription="Acceleration applied to the device, including the force of gravity."
            stateField={sensorData.sensor_accelerometer}
            field="sensor_accelerometer"
            modeState="sensor"
          />

          {sensorData.sensor_accelerometer ? (
            SensorAccelerometerSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Barometer"
            sensorDescription="Ambient air pressure."
            stateField={sensorData.sensor_barometer}
            field="sensor_barometer"
            modeState="sensor"
          />

          {sensorData.sensor_barometer ? SensorBarometerSubContent() : <div />}

          <SensorComponent
            sensorName="Bluetooth"
            sensorDescription="Smartphone's Bluetooth sensor and surrounding Bluetooth-enabled and visible devices. Includes respective RSSI dB values."
            stateField={sensorData.sensor_bluetooth}
            field="sensor_bluetooth"
            modeState="sensor"
          />

          {sensorData.sensor_bluetooth ? SensorBluetoothSubContent() : <div />}

          <SensorComponent
            sensorName="Gyroscope"
            sensorDescription="Rate or rotation in rad/s around a device’s x-, y-, and z-axis."
            stateField={sensorData.sensor_gyroscope}
            field="sensor_gyroscope"
            modeState="sensor"
          />
          {sensorData.sensor_gyroscope ? SensorGyroscopeSubContent() : <div />}

          <SensorComponent
            sensorName="Linear accelerometer"
            sensorDescription="Acceleration applied to the device, excluding the force of gravity."
            stateField={sensorData.sensor_linear_accelerometer}
            field="sensor_linear_accelerometer"
            modeState="sensor"
          />

          {sensorData.sensor_linear_accelerometer ? (
            SensorLinearAccelerometerSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Locations"
            sensorDescription="Best location estimate of the users’ current location, based on an algorithm that results in minimum battery impact."
            stateField={sensorData.sensor_locations}
            field="sensor_locations"
            modeState="sensor"
          />

          {sensorData.sensor_locations ? SensorLocationsSubContent() : <div />}

          <SensorComponent
            sensorName="Magnetometer"
            sensorDescription="Geomagnetic field strength around the device."
            stateField={sensorData.sensor_magnetometer}
            field="sensor_magnetometer"
            modeState="sensor"
          />

          {sensorData.sensor_magnetometer ? (
            SensorMagnetometerSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Network"
            sensorDescription="Information on the network sensors availability of the device. These include use of airplane mode, Wi-Fi, Bluetooth, GPS, mobile, and WIMAX status as well as internet availability."
            stateField={sensorData.sensor_network}
            field="sensor_network"
            modeState="sensor"
          />

          {sensorData.sensor_network ? SensorNetworkSubContent() : <div />}

          <SensorComponent
            sensorName="Processor"
            sensorDescription="Processor load."
            stateField={sensorData.sensor_processor}
            field="sensor_processor"
            modeState="sensor"
          />

          {sensorData.sensor_processor ? SensorProcessorSubContent() : <div />}

          <SensorComponent
            sensorName="Rotation"
            sensorDescription="Orientation of the device as a combination of an angle and an axis."
            stateField={sensorData.sensor_rotation}
            field="sensor_rotation"
            modeState="sensor"
          />

          {sensorData.sensor_rotation ? SensorRotationSubContent() : <div />}

          <SensorComponent
            sensorName="Significant Motion"
            sensorDescription="Motion co-processor signal for significant movement changes."
            stateField={sensorData.ios_significant_motion}
            field="ios_significant_motion"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Wi-Fi"
            sensorDescription="The device’s Wi-Fi sensor, current AP, and surrounding Wi-Fi visible devices with respective RSSI dB values."
            stateField={sensorData.sensor_wifi}
            field="sensor_wifi"
            modeState="sensor"
          />

          {sensorData.sensor_wifi ? SensorWifiSubContent() : <div />}
        </div>

        <div className="border">
          <p className="title">Android-only sensors</p>
          <SensorComponent
            sensorName="Gravity"
            sensorDescription="Force of gravity applied to the device, provides a three dimensional vector indicating the direction and magnitude of gravity."
            stateField={sensorData.sensor_gravity}
            field="sensor_gravity"
            modeState="sensor"
          />

          {sensorData.sensor_gravity ? SensorGravitySubContent() : <div />}

          <SensorComponent
            sensorName="Light"
            sensorDescription="Level of ambient light."
            stateField={sensorData.sensor_light}
            field="sensor_light"
            modeState="sensor"
          />

          {sensorData.sensor_light ? SensorLightSubContent() : <div />}

          <SensorComponent
            sensorName="Proximity"
            sensorDescription="Android-only proximity sensor (near/far)."
            stateField={sensorData.sensor_proximity}
            field="sensor_proximity"
            modeState="sensor"
          />

          {sensorData.sensor_proximity ? SensorProximitySubContent() : <div />}

          <SensorComponent
            sensorName="Temperature"
            sensorDescription="Ambient air temperature in Celsius (˚C). Not many devices have this sensor available."
            stateField={sensorData.sensor_temperature}
            field="sensor_temperature"
            modeState="sensor"
          />

          {sensorData.sensor_temperature ? (
            SensorTemperatureSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Applications"
            sensorDescription="Application usage and incoming notifications on the device."
            stateField={sensorData.sensor_application}
            field="sensor_application"
            modeState="sensor"
          />

          {sensorData.sensor_application ? (
            SensorApplicationSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Installations"
            sensorDescription="Application installations, removal, and updates."
            stateField={sensorData.sensor_installation}
            field="sensor_installation"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Telephony"
            sensorDescription="Information on the mobile phone capabilities of the device, connected cell towers, and neighboring towers."
            stateField={sensorData.sensor_telephony}
            field="sensor_telephony"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="MQTT"
            sensorDescription="MQTT transport for realtime sensor updates."
            stateField={sensorData.status_mqtt}
            field="status_mqtt"
            modeState="sensor"
          />
          {sensorData.status_mqtt ? SensorMqttSubContent() : <div />}

          <SensorComponent
            sensorName="Screenshot"
            sensorDescription="Smartphone screenshot capture."
            stateField={sensorData.sensor_screenshot}
            field="sensor_screenshot"
            modeState="sensor"
          />
          {sensorData.sensor_screenshot ? (
            SensorScreenshotSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Taking Note"
            sensorDescription="Allow participants to take notes. Maximum length of each note is 10000 characters."
            stateField={sensorData.sensor_notes}
            field="sensor_notes"
            modeState="sensor"
          />
        </div>

        <div className="border">
          <p className="title">iOS-only sensors</p>
          <SensorComponent
            sensorName="Activity Recognition"
            sensorDescription="Detect physical activity (walking, running, driving, etc.) using Google's activity recognition API"
            stateField={sensorData.status_plugin_google_activity_recognition}
            field="status_plugin_google_activity_recognition"
            modeState="sensor"
          />
          {sensorData.status_plugin_google_activity_recognition ? (
            PluginActivityRecognitionSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Contacts"
            sensorDescription="Periodically sync the device contacts list (hashed for privacy)"
            stateField={sensorData.status_plugin_contacts}
            field="status_plugin_contacts"
            modeState="sensor"
          />
          {sensorData.status_plugin_contacts ? (
            PluginContactsListSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Fitbit"
            sensorDescription="Sync Fitbit wearable data (steps, heart rate, sleep) via the Fitbit API"
            stateField={sensorData.status_plugin_fitbit}
            field="status_plugin_fitbit"
            modeState="sensor"
          />
          {sensorData.status_plugin_fitbit ? PluginFitbitSubContent() : <div />}

          <SensorComponent
            sensorName="Google Login"
            sensorDescription="Authenticate participants with their Google account"
            stateField={sensorData.status_plugin_google_login}
            field="status_plugin_google_login"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Conversation"
            sensorDescription="Detect conversational audio events without recording content"
            stateField={sensorData.status_plugin_studentlife_audio}
            field="status_plugin_studentlife_audio"
            modeState="sensor"
          />
          {sensorData.status_plugin_studentlife_audio ? (
            PluginConversationsSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Fused Location"
            sensorDescription="High-accuracy location using Google's fused location provider (GPS + network)"
            stateField={sensorData.status_google_fused_location}
            field="status_google_fused_location"
            modeState="sensor"
          />
          {sensorData.status_google_fused_location ? (
            PluginGoogleFusedLocationSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Device Usage"
            sensorDescription="Track app usage and screen-on/off events"
            stateField={sensorData.status_plugin_device_usage}
            field="status_plugin_device_usage"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Calendar"
            sensorDescription="Log calendar events (title, location, dates)."
            stateField={sensorData.status_plugin_calendar}
            field="status_plugin_calendar"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Google Calendar ESM"
            sensorDescription="Schedule ESM questionnaires using iOS calendar events (Google Calendar ESM scheduler)."
            stateField={sensorData.status_ios_esm_scheduler}
            field="status_ios_esm_scheduler"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Headphone Motion"
            sensorDescription="Log motion sensor data from AirPods and compatible headphones."
            stateField={sensorData.status_plugin_headphone_motion}
            field="status_plugin_headphone_motion"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="HealthKit"
            sensorDescription="Sync HealthKit data (steps, sleep, heart rate, workouts, etc.)."
            stateField={sensorData.status_health_kit}
            field="status_health_kit"
            modeState="sensor"
          />
          {sensorData.status_health_kit ? PluginHealthKitSubContent() : <div />}

          <SensorComponent
            sensorName="Heart Rate (BLE)"
            sensorDescription="Measure heart rate via a Bluetooth Low Energy wearable sensor."
            stateField={sensorData.status_plugin_ble_heartrate}
            field="status_plugin_ble_heartrate"
            modeState="sensor"
          />
          {sensorData.status_plugin_ble_heartrate ? (
            PluginBLEHeartRateSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="NTP"
            sensorDescription="Sync and log the device clock offset against NTP servers."
            stateField={sensorData.status_plugin_ntptime}
            field="status_plugin_ntptime"
            modeState="sensor"
          />

          <SensorComponent
            sensorName="Pedometer"
            sensorDescription="Log step count, distance, floors climbed, and cadence via CoreMotion."
            stateField={sensorData.status_plugin_ios_pedometer}
            field="status_plugin_ios_pedometer"
            modeState="sensor"
          />
          {sensorData.status_plugin_ios_pedometer ? (
            PluginIosPedometerSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Push Notification"
            sensorDescription="Enable push notification delivery to study participants."
            stateField={sensorData.status_push_notification}
            field="status_push_notification"
            modeState="sensor"
          />
          {sensorData.status_push_notification ? (
            PluginPushNotificationSubContent()
          ) : (
            <div />
          )}
        </div>

        <div className="border">
          <p className="title">Shared plugins</p>
          <SensorComponent
            sensorName="ESM Scheduler Plugin"
            sensorDescription="Schedule and deliver ESM questionnaires to participants"
            stateField={sensorData.status_plugin_esm_scheduler}
            field="status_plugin_esm_scheduler"
            modeState="sensor"
          />
          {sensorData.status_plugin_esm_scheduler ? (
            <Grid container spacing={2} sx={{ mt: 1, mb: 2, ml: "10%" }}>
              <Grid>
                <Button
                  color="main"
                  variant="outlined"
                  onClick={() => {
                    navigateTo("/study/questions");
                  }}
                >
                  EDIT ESM QUESTIONS
                </Button>
              </Grid>
              <Grid>
                <Button
                  color="main"
                  variant="outlined"
                  onClick={() => {
                    navigateTo("/study/schedule_configuration");
                  }}
                >
                  EDIT ESM SCHEDULES
                </Button>
              </Grid>
            </Grid>
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="Ambient Noise Plugin"
            sensorDescription="Ambient noise sampling plugin for smartphones"
            stateField={sensorData.status_plugin_ambient_noise}
            field="status_plugin_ambient_noise"
            modeState="sensor"
          />
          {sensorData.status_plugin_ambient_noise ? (
            PluginAmbientNoiseSubContent()
          ) : (
            <div />
          )}

          <SensorComponent
            sensorName="OpenWeather Plugin"
            sensorDescription="Fetch local weather data using OpenWeather API"
            stateField={sensorData.status_plugin_openweather}
            field="status_plugin_openweather"
            modeState="sensor"
          />
          {sensorData.status_plugin_openweather ? (
            PluginOpenWeatherSubContent()
          ) : (
            <div />
          )}
        </div>

        <Box sx={{ width: "100%" }} mt={5} marginBottom={5}>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 23 }}
          >
            <Grid xs={6}>
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/questions");
                }}
              >
                BACK
              </Button>
            </Grid>
            <Grid xs />
            <Grid xs="auto">
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/overview");
                  console.log(sensorData);
                }}
              >
                NEXT STEP: OVERVIEW
              </Button>
            </Grid>
          </Grid>
        </Box>
      </div>
    </ThemeProvider>
  );
}
