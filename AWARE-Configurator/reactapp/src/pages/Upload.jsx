import "./Upload.css";
import { Button } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useSetRecoilState } from "recoil";
import React, { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader/PageHeader";
import {
  accelerometerState,
  applicationSensorState,
  barometerState,
  bluetoothState,
  communicationSensorState,
  createTimeState,
  databaseInformationState,
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
  studyFormQuestionsState,
  studyFormScheduleConfigurationState,
  studyFormStudyInformationState,
  studyIdState,
  temperatureState,
  timezoneState,
  wifiState,
  screenshotSensorState,
  pluginSensorState,
} from "../functions/atom";
import Axios from "../functions/axiosSettings";
import { SET_SCHEDULES } from "../components/ScheduleComponent/ScheduleComponent";
import { padding } from "../functions/utils";

const STUDY_CONFIG_URL = "/studies/files/studyConfig.json";
const FUSED_LOCATION_ACCURACY_VALUES = [100, 101, 102, 104, 105];

function normalizeFusedLocationAccuracy(value) {
  const numeric = Number(value);
  return FUSED_LOCATION_ACCURACY_VALUES.includes(numeric) ? numeric : 102;
}

export default function Upload() {
  Axios({
    method: "get",
    url: "get_token/",
  });

  const navigateTo = useNavigate();

  const setStudyId = useSetRecoilState(studyIdState);
  const setCreateTime = useSetRecoilState(createTimeState);
  const setStudyInformation = useSetRecoilState(studyFormStudyInformationState);
  const setDatabaseInfo = useSetRecoilState(databaseInformationState);
  const setQuestions = useSetRecoilState(studyFormQuestionsState);
  const setSchedules = useSetRecoilState(studyFormScheduleConfigurationState);
  const setSensorData = useSetRecoilState(sensorDataState);
  const setApplicationSensor = useSetRecoilState(applicationSensorState);
  const setScreenData = useSetRecoilState(screenSensorState);
  const setAccelerometerData = useSetRecoilState(accelerometerState);
  const setBarometerData = useSetRecoilState(barometerState);
  const setBluetoothData = useSetRecoilState(bluetoothState);
  const setGravityData = useSetRecoilState(gravityState);
  const setGyroscopeData = useSetRecoilState(gyroscopeState);
  const setLightData = useSetRecoilState(lightState);
  const setLinearAccelerometerData = useSetRecoilState(
    linearAccelerometerState
  );
  const setLocationsData = useSetRecoilState(locationsState);
  const setMagnetometerData = useSetRecoilState(magnetometerState);
  const setNetworkData = useSetRecoilState(networkState);
  const setProximityData = useSetRecoilState(proximityState);
  const setTemperatureData = useSetRecoilState(temperatureState);
  const setRotationData = useSetRecoilState(rotationState);
  const setWifiData = useSetRecoilState(wifiState);
  const setTimezoneData = useSetRecoilState(timezoneState);
  const setCommunicationData = useSetRecoilState(communicationSensorState);
  const setScreenshotData = useSetRecoilState(screenshotSensorState);
  const setProcessorData = useSetRecoilState(processorState);
  const setPluginData = useSetRecoilState(pluginSensorState);
  const [loadState, setLoadState] = useState({
    status: "loading",
    message: `Loading ${STUDY_CONFIG_URL}...`,
  });

  const readJsonObject = (strValue) => {
    const jsonValue = JSON.parse(strValue);
    const { _id: studyId } = jsonValue;

    setStudyId(studyId);
    setStudyInformation(jsonValue.study_info);
    setDatabaseInfo(jsonValue.database || {});
    setCreateTime(jsonValue.createdAt);

    setQuestions(
      jsonValue.questions.map((question) => {
        const newQuestion = { ...question };
        delete newQuestion.id;
        return question;
      })
    );

    setSchedules(
      jsonValue.schedules.map((schedule) => {
        const newSchedule = {};
        newSchedule.title = schedule.title;
        newSchedule.type = SET_SCHEDULES;
        newSchedule.esm_keep = schedule.esm_keep;
        newSchedule.expiration = schedule.expiration !== undefined ? schedule.expiration : 60;
        newSchedule.notification_body = schedule.notification_body || "Tap to answer";
        newSchedule.questions = {};
        for (let i = 0; i < jsonValue.questions.length; i += 1) {
          const question = jsonValue.questions[i];
          const qId = question.id;
          for (let j = 0; j < schedule.questions.length; j += 1) {
            const selectedId = schedule.questions[j];
            if (qId === selectedId) {
              newSchedule.questions[qId] = true;
            }
          }
        }

        newSchedule.hours = {};
        const hoursSource = Array.isArray(schedule.hours) ? schedule.hours : [];
        for (let i = 0; i < hoursSource.length; i += 1) {
          const hour = hoursSource[i];
          newSchedule.hours[`${padding(hour, 2)}:00`] = true;
        }

        return newSchedule;
      })
    );

    const sensorData = {};
    const applicationSensor = {};
    const screenData = {};
    const accelerometerData = {};
    const barometerData = {};
    const bluetoothData = {};
    const gravityData = {};
    const gyroscopeData = {};
    const lightData = {};
    const linearAccelerometerData = {};
    const locationsData = {};
    const magnetometerData = {};
    const networkData = {};
    const proximityData = {};
    const temperatureData = {};
    const rotationData = {};
    const wifiData = {};
    const timezoneData = {};
    const communicationData = {};
    const screenshotData = {};
    const processorData = {};
    const pluginData = {};
    const iosSensors = jsonValue.ios_sensors || {};
    const iosPlugins = jsonValue.ios_plugins || {};
    const iosPluginSettings = jsonValue.ios_plugin_settings || {};

    sensorData.ios_significant_motion =
      iosSensors.significant_motion !== undefined
        ? iosSensors.significant_motion
        : false;
    sensorData.ios_websocket =
      iosSensors.websocket !== undefined ? iosSensors.websocket : false;
    sensorData.ios_mqtt =
      iosSensors.mqtt !== undefined ? iosSensors.mqtt : false;

    sensorData.status_plugin_calendar = iosPlugins.plugin_calendar !== undefined ? iosPlugins.plugin_calendar : false;
    sensorData.status_ios_esm_scheduler = iosPlugins.plugin_esm_scheduler !== undefined ? iosPlugins.plugin_esm_scheduler : false;
    sensorData.status_plugin_headphone_motion = iosPlugins.plugin_headphone_motion !== undefined ? iosPlugins.plugin_headphone_motion : false;
    sensorData.status_health_kit = iosPlugins.plugin_health_kit !== undefined ? iosPlugins.plugin_health_kit : false;
    sensorData.status_plugin_ble_heartrate = iosPlugins.plugin_ble_heartrate !== undefined ? iosPlugins.plugin_ble_heartrate : false;
    sensorData.status_plugin_ntptime = iosPlugins.plugin_ntptime !== undefined ? iosPlugins.plugin_ntptime : false;
    sensorData.status_plugin_ios_pedometer = iosPlugins.plugin_ios_pedometer !== undefined ? iosPlugins.plugin_ios_pedometer : false;
    sensorData.status_push_notication = iosPlugins.plugin_push_notification !== undefined ? iosPlugins.plugin_push_notification : false;

    if (iosPluginSettings.frequency_health_kit !== undefined) pluginData.frequency_health_kit = iosPluginSettings.frequency_health_kit;
    if (iosPluginSettings.preperiod_days_health_kit !== undefined) pluginData.preperiod_days_health_kit = iosPluginSettings.preperiod_days_health_kit;
    if (iosPluginSettings.plugin_ble_heartrate_interval_min !== undefined) pluginData.plugin_ble_heartrate_interval_min = iosPluginSettings.plugin_ble_heartrate_interval_min;
    if (iosPluginSettings.plugin_ble_heartrate_active_time_sec !== undefined) pluginData.plugin_ble_heartrate_active_time_sec = iosPluginSettings.plugin_ble_heartrate_active_time_sec;
    if (iosPluginSettings.frequency_ios_pedometer !== undefined) pluginData.frequency_ios_pedometer = iosPluginSettings.frequency_ios_pedometer;
    if (iosPluginSettings.preperiod_days_ios_pedometer !== undefined) pluginData.preperiod_days_ios_pedometer = iosPluginSettings.preperiod_days_ios_pedometer;
    if (iosPluginSettings.plugin_push_notification_server !== undefined) pluginData.plugin_push_notification_server = iosPluginSettings.plugin_push_notification_server;

    for (let i = 0; i < jsonValue.sensors.length; i += 1) {
      const { setting, value } = jsonValue.sensors[i];
      switch (setting) {
        case "webservice_wifi_only":
          sensorData.wifi_only = value;
          break;
        case "webservice_charging":
          sensorData.charging_only = value;
          break;
        case "frequency_webservice":
          sensorData.offload_frequency = value;
          break;
        case "frequency_clean_old_data":
          sensorData.clean_data_freq = value;
          break;
        case "webservice_silent":
          sensorData.no_sync_notify = value;
          break;
        case "fallback_network":
          sensorData.fallback_network = value;
          break;
        case "remind_to_charge":
          sensorData.charge_reminder = value;
          break;
        case "foreground_priority":
          sensorData.foreground_priority = value;
          break;
        case "debug_flag":
          sensorData.debug_flag = value;
          break;
        case "frequency_sync_config":
          sensorData.config_update_freq = value;
          break;
        case "enable_config_update":
          sensorData.setting_update = value;
          break;
        case "status_mqtt":
          sensorData.status_mqtt = value;
          break;
        case "mqtt_server":
          sensorData.mqtt_server = value;
          break;
        case "mqtt_port":
          sensorData.mqtt_port = value;
          break;
        case "mqtt_username":
          sensorData.mqtt_username = value;
          break;
        case "mqtt_password":
          sensorData.mqtt_password = value;
          break;
        case "mqtt_keep_alive":
          sensorData.mqtt_keep_alive = value;
          break;
        case "mqtt_qos":
          sensorData.mqtt_qos = value;
          break;
        case "webservice_simple":
          sensorData.webservice_simple = value;
          break;
        case "webservice_remove_data":
          sensorData.webservice_remove_data = value;
          break;
        case "debug_db_slow":
          sensorData.debug_db_slow = value;
          break;
        case "status_applications":
          sensorData.sensor_application = value;
          break;
        case "status_notifications":
          applicationSensor.notifications = value;
          break;
        case "status_crashes":
          applicationSensor.crashes = value;
          break;
        case "frequency_applications":
          applicationSensor.frequency_applications = value;
          break;
        case "status_keyboard":
          applicationSensor.keyboard = value;
          break;
        case "mask_keyboard":
          applicationSensor.mask_keyboard = value;
          break;
        case "mask_notification":
          applicationSensor.mask_notification = value;
          break;
        case "mask_touch_text":
          applicationSensor.mask_touch_text = value;
          break;
        case "status_screentext":
          applicationSensor.status_screentext = value;
          break;
        case "package_specification":
          applicationSensor.package_specification = value;
          break;
        case "package_names":
          applicationSensor.package_names = value;
          break;
        case "status_battery":
          sensorData.sensor_battery = value;
          break;
        case "communication":
          sensorData.sensor_communication = value;
          break;
        case "status_communication_events":
          communicationData.events = value;
          break;
        case "status_calls":
          communicationData.calls = value;
          if (value) {
            sensorData.sensor_communication = true;
          }
          break;
        case "status_messages":
          communicationData.messages = value;
          break;
        case "status_installations":
          sensorData.sensor_installation = value;
          break;
        case "status_screen":
          sensorData.sensor_screen = value;
          break;
        case "status_touch":
          screenData.sensor_touch = value;
          break;
        case "status_telephony":
          sensorData.sensor_telephony = value;
          break;
        case "status_timezone":
          sensorData.sensor_timezone = value;
          break;
        case "frequency_timezone":
          timezoneData.frequency_timezone = value;
          break;
        case "status_accelerometer":
          sensorData.sensor_accelerometer = value;
          break;
        case "frequency_accelerometer":
          accelerometerData.frequency_sample_accelerometer = value;
          break;
        case "threshold_accelerometer":
          accelerometerData.threshold = value;
          break;
        case "frequency_accelerometer_enforce":
          accelerometerData.enforce = value;
          break;
        case "status_barometer":
          sensorData.sensor_barometer = value;
          break;
        case "frequency_barometer":
          barometerData.frequency_sample_barometer = value;
          break;
        case "threshold_barometer":
          barometerData.threshold = value;
          break;
        case "frequency_barometer_enforce":
          barometerData.enforce = value;
          break;
        case "status_bluetooth":
          sensorData.sensor_bluetooth = value;
          break;
        case "frequency_bluetooth":
          bluetoothData.frequency_bluetooth = value;
          break;
        case "status_gravity":
          sensorData.sensor_gravity = value;
          break;
        case "frequency_gravity":
          gravityData.frequency_gravity = value;
          break;
        case "threshold_gravity":
          gravityData.threshold = value;
          break;
        case "frequency_gravity_enforce":
          gravityData.enforce = value;
          break;
        case "status_gyroscope":
          sensorData.sensor_gyroscope = value;
          break;
        case "frequency_gyroscope":
          gyroscopeData.frequency_gyroscope = value;
          break;
        case "threshold_gyroscope":
          gyroscopeData.threshold = value;
          break;
        case "frequency_gyroscope_enforce":
          gyroscopeData.enforce = value;
          break;
        case "status_light":
          sensorData.sensor_light = value;
          break;
        case "frequency_light":
          lightData.frequency_light = value;
          break;
        case "threshold_light":
          lightData.threshold = value;
          break;
        case "frequency_light_enforce":
          lightData.enforce = value;
          break;
        case "status_linear_accelerometer":
          sensorData.sensor_linear_accelerometer = value;
          break;
        case "frequency_linear_accelerometer":
          linearAccelerometerData.frequency_linear_accelerometer = value;
          break;
        case "threshold_linear_accelerometer":
          linearAccelerometerData.threshold = value;
          break;
        case "frequency_linear_accelerometer_enforce":
          linearAccelerometerData.enforce = value;
          break;
        case "location":
          sensorData.sensor_locations = value;
          break;
        case "status_location_gps":
          locationsData.gps = value;
          break;
        case "status_location_network":
          locationsData.network = value;
          break;
        case "frequency_location_gps":
          locationsData.frequency_gps = value;
          break;
        case "frequency_location_network":
          locationsData.frequency_network = value;
          break;
        case "min_location_gps_accuracy":
          locationsData.min_gps_freq = value;
          break;
        case "min_location_network_accuracy":
          locationsData.min_network_freq = value;
          break;
        case "location_expiration_time":
          locationsData.expiration = value;
          break;
        case "status_location_passive":
          locationsData.passive = value;
          break;
        case "location_save_all":
          locationsData.save_all = value;
          break;
        case "status_magnetometer":
          sensorData.sensor_magnetometer = value;
          break;
        case "frequency_magnetometer":
          magnetometerData.frequency_magnetometer = value;
          break;
        case "threshold_magnetometer":
          magnetometerData.threshold = value;
          break;
        case "frequency_magnetometer_enforce":
          magnetometerData.enforce = value;
          break;
        case "network":
          sensorData.sensor_network = value;
          break;
        case "status_network_events":
          networkData.events = value;
          break;
        case "status_network_traffic":
          networkData.traffic = value;
          break;
        case "frequency_network_traffic":
          networkData.frequency_network_traffic = value;
          break;
        case "status_significant_motion":
          sensorData.ios_significant_motion = value;
          break;
        case "status_processor":
          sensorData.sensor_processor = value;
          break;
        case "frequency_processor":
          processorData.frequency_processor = value;
          break;
        case "status_proximity":
          sensorData.sensor_proximity = value;
          break;
        case "frequency_proximity":
          proximityData.frequency_proximity = value;
          break;
        case "threshold_proximity":
          proximityData.threshold = value;
          break;
        case "frequency_proximity_enforce":
          proximityData.enforce = value;
          break;
        case "status_rotation":
          sensorData.sensor_rotation = value;
          break;
        case "frequency_rotation":
          rotationData.frequency_rotation = value;
          break;
        case "threshold_rotation":
          rotationData.threshold = value;
          break;
        case "frequency_rotation_enforce":
          rotationData.enforce = value;
          break;
        case "status_temperature":
          sensorData.sensor_temperature = value;
          break;
        case "frequency_temperature":
          temperatureData.frequency_temperature = value;
          break;
        case "threshold_temperature":
          temperatureData.threshold = value;
          break;
        case "frequency_temperature_enforce":
          temperatureData.enforce = value;
          break;
        case "status_wifi":
          sensorData.sensor_wifi = value;
          break;
        case "frequency_wifi":
          wifiData.frequency_wifi = value;
          break;
        case "status_esm":
          break;
        case "status_webservice":
          break;
        case "status_screenshot":
          sensorData.sensor_screenshot = value;
          break;
        case "capture_time_interval":
          screenshotData.capture_time_interval = value;
          break;
        case "compress_rate":
          screenshotData.compress_rate = value;
          break;
        case "status_screenshot_local_storage":
          screenshotData.status_screenshot_local_storage = value;
          break;
        case "screenshot_package_names":
          applicationSensor.screenshot_package_names = value;
          break;
        case "screenshot_package_specification":
          applicationSensor.screenshot_package_specification = value;
          break;
        case "status_notes":
          sensorData.sensor_notes = value;
          break;
        case "status_plugin_ambient_noise":
          sensorData.status_plugin_ambient_noise = value;
          break;
        case "frequency_plugin_ambient_noise":
          pluginData.frequency_plugin_ambient_noise = value;
          break;
        case "plugin_ambient_noise_sample_size":
          pluginData.plugin_ambient_noise_sample_size = value;
          break;
        case "plugin_ambient_noise_silence_threshold":
          pluginData.plugin_ambient_noise_silence_threshold = value;
          break;
        case "status_plugin_openweather":
          sensorData.status_plugin_openweather = value;
          break;
        case "plugin_openweather_frequency":
          pluginData.plugin_openweather_frequency = value;
          break;
        case "plugin_openweather_api_key":
          pluginData.plugin_openweather_api_key = value;
          break;
        case "plugin_openweather_measurement_units":
          pluginData.plugin_openweather_measurement_units = value;
          break;
        case "status_plugin_google_activity_recognition":
          sensorData.status_plugin_google_activity_recognition = value;
          break;
        case "frequency_plugin_google_activity_recognition":
          pluginData.frequency_plugin_google_activity_recognition = value;
          break;
        case "status_plugin_esm_scheduler":
          sensorData.status_plugin_esm_scheduler = value;
          break;
        case "status_plugin_fitbit":
          sensorData.status_plugin_fitbit = value;
          break;
        case "units_plugin_fitbit":
          pluginData.units_plugin_fitbit = value;
          break;
        case "fitbit_granularity":
          pluginData.fitbit_granularity = value;
          break;
        case "fitbit_hr_granularity":
          pluginData.fitbit_hr_granularity = value;
          break;
        case "plugin_fitbit_frequency":
          pluginData.plugin_fitbit_frequency = value;
          break;
        case "api_key_plugin_fitbit":
          pluginData.api_key_plugin_fitbit = value;
          break;
        case "api_secret_plugin_fitbit":
          pluginData.api_secret_plugin_fitbit = value;
          break;
        case "status_plugin_contacts":
          sensorData.status_plugin_contacts = value;
          break;
        case "frequency_plugin_contacts":
          pluginData.frequency_plugin_contacts = value;
          break;
        case "status_plugin_google_login":
          sensorData.status_plugin_google_login = value;
          break;
        case "status_google_fused_location":
          sensorData.status_google_fused_location = value;
          break;
        case "frequency_google_fused_location":
          pluginData.frequency_google_fused_location = value;
          break;
        case "max_frequency_google_fused_location":
          pluginData.max_frequency_google_fused_location = value;
          break;
        case "fallback_location_timeout":
          pluginData.fallback_location_timeout = value;
          break;
        case "accuracy_google_fused_location":
          pluginData.accuracy_google_fused_location =
            normalizeFusedLocationAccuracy(value);
          break;
        case "status_plugin_device_usage":
          sensorData.status_plugin_device_usage = value;
          break;
        case "status_plugin_studentlife_audio":
          sensorData.status_plugin_studentlife_audio = value;
          break;
        case "plugin_conversations_delay":
          pluginData.plugin_conversations_delay = value;
          break;
        case "plugin_conversations_off_duty":
          pluginData.plugin_conversations_off_duty = value;
          break;
        case "plugin_conversations_length":
          pluginData.plugin_conversations_length = value;
          break;
        case "plugin_ambient_noise_no_raw":
          pluginData.plugin_ambient_noise_no_raw = value;
          break;
        default:
      }
    }

    setSensorData(sensorData);
    setApplicationSensor(applicationSensor);
    setScreenData(screenData);
    setAccelerometerData(accelerometerData);
    setBarometerData(barometerData);
    setBluetoothData(bluetoothData);
    setGravityData(gravityData);
    setGyroscopeData(gyroscopeData);
    setLightData(lightData);
    setLinearAccelerometerData(linearAccelerometerData);
    setLocationsData(locationsData);
    setMagnetometerData(magnetometerData);
    setNetworkData(networkData);
    setProximityData(proximityData);
    setTemperatureData(temperatureData);
    setRotationData(rotationData);
    setWifiData(wifiData);
    setTimezoneData(timezoneData);
    setCommunicationData(communicationData);
    setScreenshotData(screenshotData);
    setProcessorData(processorData);
    setPluginData(pluginData);
    navigateTo("/study/study_information");
  };

  useEffect(() => {
    let isActive = true;

    fetch(STUDY_CONFIG_URL, {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to load ${STUDY_CONFIG_URL}`);
        }
        return response.text();
      })
      .then((text) => {
        if (!isActive) {
          return;
        }
        readJsonObject(text);
      })
      .catch((error) => {
        if (!isActive) {
          return;
        }
        setLoadState({
          status: "error",
          message: error.message,
        });
      });

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <div>
      <PageHeader />
      <div className="main_vertical_layout">
        <p className="main_title">Open study configuration</p>
        <p className="main_description">
          The configurator automatically loads the shared Android study file and
          opens it for editing.
        </p>
        <p className="main_description">{loadState.message}</p>
        {loadState.status === "error" && (
          <Button
            variant="contained"
            onClick={() => {
              window.location.reload();
            }}
          >
            Retry
          </Button>
        )}
        <Button
          onClick={() => {
            navigateTo("/main");
          }}
        >
          Back to main page
        </Button>
      </div>
    </div>
  );
}
