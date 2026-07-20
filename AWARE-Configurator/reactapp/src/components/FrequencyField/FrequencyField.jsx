import React, { useState, useEffect } from "react";
import "./FrequencyField.css";
import { Radio, RadioGroup, TextField } from "@mui/material";
import FormControlLabel from "@mui/material/FormControlLabel";
import { useRecoilState } from "recoil";
import Grid from "@mui/material/Unstable_Grid2";
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
  temperatureState,
  timezoneState,
  wifiState,
  screenshotSensorState,
  pluginSensorState,
} from "../../functions/atom";

// Presets is an optional array of { key, value, label, detail } used to render
// research-justified rate options above the raw numeric field. Each preset's
// `label` names the use case it's good for (e.g. "Fall detection") and
// `detail` states the actual value plus the tradeoff/citation backing it
// (e.g. "50 Hz - needed for short-duration impact events; highest battery
// cost of this sensor's options"). The number of presets is deliberately not
// fixed at five - sensors whose literature only supports two or three
// meaningfully distinct rates only get that many, plus Custom. Sensors that
// don't pass presets keep the original plain-text-field behaviour.
function findPresetKey(presets, value) {
  if (!presets || presets.length === 0) return "custom";
  const numeric = Number(value);
  const match = presets.find((preset) => Number(preset.value) === numeric);
  return match ? match.key : "custom";
}

function FrequencyField(inputs) {
  const {
    id,
    title,
    inputLabel,
    defaultNum,
    description,
    field,
    studyField,
    modeState,
    presets,
    allowZero,
  } = inputs;

  const initialValue = studyField || defaultNum.toString();

  const [localValue, setLocalValue] = useState(initialValue);
  const [presetSelection, setPresetSelection] = useState(
    findPresetKey(presets, initialValue)
  );

  useEffect(() => {
    const nextValue = studyField || defaultNum.toString();
    setLocalValue(nextValue);
    setPresetSelection(findPresetKey(presets, nextValue));
  }, [studyField, defaultNum, presets]);

  const [sensorData, setSensorData] = useRecoilState(sensorDataState);
  const [applicationSensor, setApplicationSensor] = useRecoilState(
    applicationSensorState
  );
  const [screenData, setScreenData] = useRecoilState(screenSensorState);
  const [communicationData, setCommunicationData] = useRecoilState(
    communicationSensorState
  );
  const [timezoneData, setTimezoneData] = useRecoilState(timezoneState);
  const [accelerometerData, setAccelerometerData] =
    useRecoilState(accelerometerState);
  const [barometerData, setBarometerData] = useRecoilState(barometerState);
  const [bluetoothData, setBluetoothData] = useRecoilState(bluetoothState);
  const [gravityData, setGravityData] = useRecoilState(gravityState);
  const [gyroscopeData, setGyroscopeData] = useRecoilState(gyroscopeState);
  const [lightData, setLightData] = useRecoilState(lightState);
  const [linearAccelerometerData, setLinearAccelerometerData] = useRecoilState(
    linearAccelerometerState
  );
  const [locationsData, setLocationsData] = useRecoilState(locationsState);
  const [magnetometerData, setMagnetometerData] =
    useRecoilState(magnetometerState);
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

  const [pluginData, setPluginData] = useRecoilState(pluginSensorState);

  const updateScreenshotData = (fieldName, value) => {
    setScreenshotData({
      ...screenshotData,
      [fieldName]: value,
    });
  };

  const updatePluginData = (fieldName, value) => {
    setPluginData({
      ...pluginData,
      [fieldName]: value,
    });
  };

  function updateStates(fieldName, value, mode) {
    const numValue = parseFloat(value);
    const isValid =
      !Number.isNaN(numValue) &&
      (numValue > 0 || (allowZero && numValue === 0));
    if (isValid) {
      switch (mode) {
        case "sensor":
          setSensorData((prevData) => ({ ...prevData, [fieldName]: numValue }));
          break;
        case "application":
          setApplicationSensor((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "screen":
          setScreenData((prevData) => ({ ...prevData, [fieldName]: numValue }));
          break;
        case "communication":
          setCommunicationData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "timezone":
          setTimezoneData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "accelerometer":
          setAccelerometerData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "barometer":
          setBarometerData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "bluetooth":
          setBluetoothData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "gravity":
          setGravityData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "gyroscope":
          setGyroscopeData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "light":
          setLightData((prevData) => ({ ...prevData, [fieldName]: numValue }));
          break;
        case "linearAccelerometer":
          setLinearAccelerometerData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "locations":
          setLocationsData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "magnetometer":
          setMagnetometerData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "network":
          setNetworkData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "processor":
          setProcessorData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "rotation":
          setRotationData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "temperature":
          setTemperatureData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "proximity":
          setProximityData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "wifi":
          setWifiData((prevData) => ({ ...prevData, [fieldName]: numValue }));
          break;
        case "screenshot":
          setScreenshotData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;
        case "plugin":
          setPluginData((prevData) => ({
            ...prevData,
            [fieldName]: numValue,
          }));
          break;

        default:
          console.warn(`Unexpected mode: ${mode}`);
          break;
      }
    }
  }

  const handleChange = (event) => {
    const newValue = event.target.value;
    setLocalValue(newValue);

    // Allow typing decimal numbers, but don't update state yet
    if (
      newValue === "" ||
      newValue === "0" ||
      newValue === "0." ||
      /^0?\.\d*$/.test(newValue)
    ) {
      return;
    }

    updateStates(field.toString(), newValue, modeState);
  };

  const handleBlur = () => {
    const numValue = parseFloat(localValue);
    const isValid =
      !Number.isNaN(numValue) &&
      (numValue > 0 || (allowZero && numValue === 0));
    if (!isValid) {
      setLocalValue(defaultNum.toString());
      updateStates(field.toString(), defaultNum, modeState);
    } else {
      setLocalValue(numValue.toString());
      updateStates(field.toString(), numValue, modeState);
    }
  };

  const handlePresetChange = (event) => {
    const key = event.target.value;
    setPresetSelection(key);

    if (key === "custom") {
      // Reset to 0 so the researcher has to consciously type their own
      // value, instead of silently inheriting whatever preset was last
      // selected (which could be mistaken for a deliberate choice).
      setLocalValue("0");
      return;
    }

    const preset = presets.find((option) => option.key === key);
    if (preset) {
      setLocalValue(preset.value.toString());
      updateStates(field.toString(), preset.value, modeState);
    }
  };

  const hasPresets = Array.isArray(presets) && presets.length > 0;

  return (
    <div className="sensor_vertical_layout">
      <Grid>
        <p className="field_name" mb={10}>
          {title}
        </p>
      </Grid>

      {hasPresets ? (
        <Grid marginTop={2}>
          <RadioGroup
            aria-labelledby={`${id}_presets`}
            name={`${id}_presets`}
            value={presetSelection}
            onChange={handlePresetChange}
          >
            {presets.map((preset) => (
              <FormControlLabel
                key={preset.key}
                value={preset.key}
                control={<Radio />}
                label={
                  <span>
                    <span>{preset.label}</span>
                    {preset.detail ? (
                      <span
                        style={{
                          display: "block",
                          fontSize: "0.8rem",
                          color: "#666",
                        }}
                      >
                        {preset.detail}
                      </span>
                    ) : null}
                  </span>
                }
              />
            ))}
            <FormControlLabel
              value="custom"
              control={<Radio />}
              label={
                <span>
                  <span>Custom</span>
                  <span
                    style={{
                      display: "block",
                      fontSize: "0.8rem",
                      color: "#666",
                    }}
                  >
                    Set your own value if none of the above match your study's
                    needs.
                  </span>
                </span>
              }
            />
          </RadioGroup>
        </Grid>
      ) : (
        <div />
      )}

      {!hasPresets || presetSelection === "custom" ? (
        <Grid marginTop={2}>
          <TextField
            id={id}
            label={inputLabel}
            value={localValue}
            type="text"
            InputLabelProps={{
              shrink: true,
            }}
            style={{ width: "100%" }}
            onChange={handleChange}
            onBlur={handleBlur}
          />
        </Grid>
      ) : (
        <div />
      )}

      {description ? (
        <p className="schedule-description">{description}</p>
      ) : (
        <div />
      )}
    </div>
  );
}

export default FrequencyField;
