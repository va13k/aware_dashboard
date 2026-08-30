import "./Overview.css";
import {
  Alert,
  AlertTitle,
  Button,
  Divider,
  ThemeProvider,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import Grid from "@mui/material/Unstable_Grid2";
import React, { useState } from "react";
import { useRecoilValue, useRecoilState } from "recoil";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
// eslint-disable-next-line import/no-extraneous-dependencies
import customisedTheme from "../functions/theme";
import {
  accelerometerState,
  applicationSensorState,
  barometerState,
  bluetoothState,
  communicationSensorState,
  createTimeState,
  databaseInformationState,
  dataflowState,
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
  noteState,
  pluginSensorState,
} from "../functions/atom";
import {
  SET_SCHEDULES,
  RANDOM_TRIGGERS,
  REPEAT_INTERVALS,
} from "../components/ScheduleComponent/ScheduleComponent";
import Axios from "../functions/axiosSettings";

const TYPE_MAP = {
  1: "Free Text",
  2: "Single Choice(Radio)",
  3: "Multiple Choice(Checkbox)",
  4: "Likert Scale",
  5: "Quick Answer",
  6: "Scale",
  7: "Numeric",
};

const FUSED_LOCATION_ACCURACY_VALUES = [100, 101, 102, 104, 105];

function normalizeFusedLocationAccuracy(value) {
  const numeric = Number(value);
  return FUSED_LOCATION_ACCURACY_VALUES.includes(numeric) ? numeric : 102;
}

export default function Overview() {
  const navigateTo = useNavigate();

  const studyInformation = useRecoilValue(studyFormStudyInformationState);
  const databaseInfo = useRecoilValue(databaseInformationState);
  const dataflow = useRecoilValue(dataflowState);
  const questions = useRecoilValue(studyFormQuestionsState);
  const schedules = useRecoilValue(studyFormScheduleConfigurationState);
  const sensorData = useRecoilValue(sensorDataState);
  const applicationSensor = useRecoilValue(applicationSensorState);
  const screenData = useRecoilValue(screenSensorState);
  const accelerometerData = useRecoilValue(accelerometerState);
  const barometerData = useRecoilValue(barometerState);
  const bluetoothData = useRecoilValue(bluetoothState);
  const gravityData = useRecoilValue(gravityState);
  const gyroscopeData = useRecoilValue(gyroscopeState);
  const lightData = useRecoilValue(lightState);
  const linearAccelerometerData = useRecoilValue(linearAccelerometerState);
  const locationsData = useRecoilValue(locationsState);
  const magnetometerData = useRecoilValue(magnetometerState);
  const networkData = useRecoilValue(networkState);
  const proximityData = useRecoilValue(proximityState);
  const temperatureData = useRecoilValue(temperatureState);
  const rotationData = useRecoilValue(rotationState);
  const wifiData = useRecoilValue(wifiState);
  const timezoneData = useRecoilValue(timezoneState);
  const communicationData = useRecoilValue(communicationSensorState);
  const studyId = useRecoilValue(studyIdState);
  const createTime = useRecoilValue(createTimeState);
  const date = new Date().toJSON();
  const screenshotData = useRecoilValue(screenshotSensorState);
  const processorData = useRecoilValue(processorState);
  const noteData = useRecoilValue(noteState);
  const pluginData = useRecoilValue(pluginSensorState);
  const [saveState, setSaveState] = useState({
    status: "idle",
    message: "",
  });
  const normalizeScheduleQuestionIds = (schedule) => {
    const selectedQuestions = schedule?.questions;
    if (Array.isArray(selectedQuestions)) {
      return [
        ...new Set(
          selectedQuestions
            .map((questionId) => parseInt(questionId, 10))
            .filter(
              (questionId) =>
                !Number.isNaN(questionId) &&
                questionId >= 1 &&
                questionId <= questions.length
            )
        ),
      ];
    }

    if (!selectedQuestions || typeof selectedQuestions !== "object") {
      return [];
    }

    const questionIds = [];
    Object.entries(selectedQuestions).forEach(([key, value]) => {
      if (value !== true && value !== "true" && value !== 1) {
        return;
      }

      const numericId = parseInt(key, 10);
      if (
        !Number.isNaN(numericId) &&
        `${numericId}` === key &&
        numericId >= 1 &&
        numericId <= questions.length
      ) {
        questionIds.push(numericId);
        return;
      }

      const questionIndex = questions.findIndex(
        (question) => question.esm_title === key
      );
      if (questionIndex >= 0) {
        questionIds.push(questionIndex + 1);
      }
    });

    return [...new Set(questionIds)];
  };

  const getScheduleQuestionLabels = (schedule) => {
    return normalizeScheduleQuestionIds(schedule).map((questionId) => {
      return questions[questionId - 1]?.esm_title || `Question ${questionId}`;
    });
  };

  const checkStudyInformationValidation = () => {
    return (
      studyInformation.study_title &&
      studyInformation.study_description &&
      studyInformation.researcher_first &&
      studyInformation.researcher_last &&
      studyInformation.researcher_contact
    );
  };

  const checkQuestionValidation = () => {
    if (questions.length === 0) return false;
    for (let i = 0; i < questions.length; i += 1) {
      const each = questions[i];
      if (!each.esm_type || !each.esm_title) {
        return false;
      }
    }
    return true;
  };

  const checkScheduleValidation = () => {
    if (schedules.length === 0) return false;
    for (let i = 0; i < schedules.length; i += 1) {
      const each = schedules[i];
      if (!each.questions || !each.title) {
        return false;
      }

      if (normalizeScheduleQuestionIds(each).length === 0) {
        return false;
      }
    }
    return true;
  };

  function displayInfo(instruction, content) {
    return (
      <Grid container rowSpacing={1} ml="10%" mt="3%" mb="3%">
        <Grid width="50%">
          <div>{instruction}</div>
        </Grid>
        <Grid width="50%">
          <div>{content}</div>
        </Grid>
      </Grid>
    );
  }

  function displaySensors(sensor, sensorName) {
    if (sensorData[sensor]) {
      return (
        <Grid width="100%" ml="10%" mt="3%">
          <div>{sensorName}</div>
        </Grid>
      );
    }
    return <div />;
  }

  const questionList = questions.map((question, idx) => {
    return (
      <div key={`question-${idx}`}>
        {displayInfo(`Question ${(idx + 1).toString()}`, question.esm_title)}
        {displayInfo("Instructions", question.instructions)}
        {displayInfo("Question type", TYPE_MAP[question.esm_type])}

        <Divider
          style={{ background: "main" }}
          // component="li"
          variant="middle"
          sx={{ marginBottom: "3%" }}
        />
      </div>
    );
  });

  const scheduleList = schedules.map((schedule, idx) => {
    return (
      <div key={`schedule-${idx}`}>
        {/* {displayInfo(`Schedule ${(idx + 1).toString()}`, schedule.title)} */}
        {/* {displayInfo(`Questions`, Object.keys(schedule.questions).join(", "))} */}

        {schedule ? (
          displayInfo(`Schedule ${(idx + 1).toString()}`, schedule.title)
        ) : (
          <div />
        )}
        {/* {console.log(schedule.questions)} */}
        {schedule.questions ? (
          displayInfo(
            `Questions`,
            getScheduleQuestionLabels(schedule).join(", ")
          )
        ) : (
          <div />
        )}
        <Divider
          style={{ background: "main" }}
          // component="li"
          variant="middle"
          sx={{ marginBottom: "3%" }}
        />
      </div>
    );
  });

  function buildResult() {
    let mqttEnabled = false;
    if (sensorData.status_mqtt !== undefined) {
      mqttEnabled = sensorData.status_mqtt;
    } else if (sensorData.ios_mqtt !== undefined) {
      mqttEnabled = sensorData.ios_mqtt;
    }

    return {
      _id: studyId,
      study_info: studyInformation,
      // Declared above the database block, because on the webservice path there is
      // no database block to carry it.
      dataflow,
      database: {
        ...databaseInfo,
        config_without_password: !!(
          "config_without_password" in databaseInfo &&
          databaseInfo.config_without_password
        ),
        // Sent only when the form actually holds an answer. A missing key means
        // this browser was never shown the control -- the served config carries it
        // on one dataflow and not the other -- and sending `false` for it would
        // turn a study's encryption off by opening a page.
        ...("require_ssl" in databaseInfo
          ? { require_ssl: !!databaseInfo.require_ssl }
          : {}),
        rootUsername: "-",
        rootPassword: "-",
      },
      createdAt: createTime,
      updatedAt: date,
      questions: [...questions].map((question, idx) => {
        return { ...question, id: idx + 1 };
      }),
      schedules: [...schedules].map((schedule) => {
        const hours = [];
        for (const key in schedule.hours) {
          if (schedule.hours[key] === true) {
            hours.push(parseInt(key.slice(0, 2), 10));
          }
        }
        const days = Object.keys(schedule.days || {}).filter(
          (day) => schedule.days[day] === true
        );

        const type = schedule.type || SET_SCHEDULES;
        const common = {
          title: schedule.title,
          type,
          // Carried over unless the study says otherwise. Without it the client
          // clears its queue on every firing: a prompt nobody answered within the
          // interval is marked replaced rather than left waiting, and a schedule
          // that fires faster than participants answer collects nothing at all.
          esm_keep: schedule.esm_keep ?? true,
          questions: normalizeScheduleQuestionIds(schedule),
          expiration:
            schedule.expiration !== undefined ? schedule.expiration : 60,
          notification_body: schedule.notification_body || "Tap to answer",
        };

        // Only the settings the chosen type actually uses are written. A study
        // that was a random schedule and became a set one would otherwise carry
        // both, and the generators downstream read whichever they find first --
        // so a stale field is a schedule that fires on a rule nobody chose.
        if (type === RANDOM_TRIGGERS) {
          return {
            ...common,
            firsthour: schedule.firsthour || "08:00",
            lasthour: schedule.lasthour || "20:00",
            randomCount: schedule.randomCount,
            randomInterval: schedule.randomInterval,
          };
        }
        if (type === REPEAT_INTERVALS) {
          return { ...common, repeatInterval: schedule.repeatInterval };
        }
        return { ...common, hours, days };
      }),
      sensors: [
        {
          setting: "webservice_wifi_only",
          value: sensorData.wifi_only ? sensorData.wifi_only : false,
        },
        {
          setting: "webservice_charging",
          value: sensorData.charging_only ? sensorData.charging_only : false,
        },
        {
          setting: "frequency_webservice",
          value: sensorData.offload_frequency
            ? sensorData.offload_frequency
            : 60,
        },
        {
          setting: "frequency_clean_old_data",
          value: sensorData.clean_data_freq ? sensorData.clean_data_freq : 0,
        },
        {
          setting: "webservice_silent",
          value: sensorData.no_sync_notify ? sensorData.no_sync_notify : false,
        },
        {
          setting: "fallback_network",
          value: sensorData.fallback_network ? sensorData.fallback_network : 30,
        },
        {
          setting: "remind_to_charge",
          value: sensorData.charge_reminder
            ? sensorData.charge_reminder
            : false,
        },
        {
          setting: "foreground_priority",
          value: sensorData.foreground_priority
            ? sensorData.foreground_priority
            : false,
        },
        {
          setting: "debug_flag",
          value: sensorData.debug_flag ? sensorData.debug_flag : false,
        },
        {
          setting: "frequency_sync_config",
          value: sensorData.config_update_freq
            ? sensorData.config_update_freq
            : 60,
        },
        {
          setting: "enable_config_update",
          value: sensorData.setting_update ? sensorData.setting_update : false,
        },
        {
          setting: "status_mqtt",
          value: sensorData.status_mqtt ? sensorData.status_mqtt : false,
        },
        {
          setting: "mqtt_server",
          value: sensorData.mqtt_server ? sensorData.mqtt_server : "",
        },
        {
          setting: "mqtt_port",
          value: sensorData.mqtt_port ? sensorData.mqtt_port : 1883,
        },
        {
          setting: "mqtt_username",
          value: sensorData.mqtt_username ? sensorData.mqtt_username : "",
        },
        {
          setting: "mqtt_password",
          value: sensorData.mqtt_password ? sensorData.mqtt_password : "",
        },
        {
          setting: "mqtt_keep_alive",
          value: sensorData.mqtt_keep_alive ? sensorData.mqtt_keep_alive : 600,
        },
        {
          setting: "mqtt_qos",
          value: sensorData.mqtt_qos ? sensorData.mqtt_qos : 2,
        },
        {
          setting: "webservice_simple",
          value: sensorData.webservice_simple
            ? sensorData.webservice_simple
            : false,
        },
        {
          setting: "webservice_remove_data",
          value: sensorData.webservice_remove_data
            ? sensorData.webservice_remove_data
            : false,
        },
        {
          setting: "debug_db_slow",
          value: sensorData.debug_db_slow ? sensorData.debug_db_slow : false,
        },

        // application
        {
          setting: "status_applications",
          value: sensorData.sensor_application
            ? sensorData.sensor_application
            : false,
        },
        {
          setting: "status_notifications",
          value: applicationSensor.notifications
            ? applicationSensor.notifications
            : false,
        },
        {
          setting: "status_crashes",
          value: applicationSensor.crashes ? applicationSensor.crashes : false,
        },
        {
          setting: "frequency_applications",
          value: applicationSensor.frequency_applications
            ? applicationSensor.frequency_applications
            : 30,
        },
        {
          setting: "status_keyboard",
          value: applicationSensor.keyboard
            ? applicationSensor.keyboard
            : false,
        },
        {
          setting: "mask_notification",
          value: applicationSensor.mask_notification
            ? applicationSensor.mask_notification
            : false,
        },
        {
          setting: "mask_keyboard",
          value: applicationSensor.mask_keyboard
            ? applicationSensor.mask_keyboard
            : false,
        },
        {
          setting: "mask_touch_text",
          value: applicationSensor.mask_touch_text
            ? applicationSensor.mask_touch_text
            : false,
        },
        {
          setting: "status_screentext",
          value: applicationSensor.status_screentext
            ? applicationSensor.status_screentext
            : false,
        },
        {
          setting: "package_specification",
          value: applicationSensor.package_specification
            ? applicationSensor.package_specification
            : "2",
        },
        {
          setting: "package_names",
          value: applicationSensor.package_names
            ? applicationSensor.package_names
            : "",
        },

        // battery
        {
          setting: "status_battery",
          value: sensorData.sensor_battery ? sensorData.sensor_battery : false,
        },

        // communication
        {
          setting: "communication",
          value: sensorData.sensor_communication
            ? sensorData.sensor_communication
            : false,
        },

        {
          setting: "status_communication_events",
          value: communicationData.events ? communicationData.events : false,
        },
        {
          setting: "status_calls",
          value: sensorData.sensor_communication
            ? sensorData.sensor_communication
            : false,
        },
        {
          setting: "status_messages",
          value: communicationData.messages
            ? communicationData.messages
            : false,
        },

        // installation
        {
          setting: "status_installations",
          value: sensorData.sensor_installation
            ? sensorData.sensor_installation
            : false,
        },
        // screen
        {
          setting: "status_screen",
          value: sensorData.sensor_screen ? sensorData.sensor_screen : false,
        },
        {
          setting: "status_touch",
          value: screenData.sensor_touch ? screenData.sensor_touch : false,
        },
        // telephony
        {
          setting: "status_telephony",
          value: sensorData.sensor_telephony
            ? sensorData.sensor_telephony
            : false,
        },

        // timezone
        {
          setting: "status_timezone",
          value: sensorData.sensor_timezone
            ? sensorData.sensor_timezone
            : false,
        },
        {
          setting: "frequency_timezone",
          value: timezoneData.frequency_timezone
            ? timezoneData.frequency_timezone
            : 20000,
        },

        // accelerometer
        {
          setting: "status_accelerometer",
          value: sensorData.sensor_accelerometer
            ? sensorData.sensor_accelerometer
            : false,
        },
        {
          setting: "frequency_accelerometer",
          value: accelerometerData.frequency_sample_accelerometer
            ? accelerometerData.frequency_sample_accelerometer
            : 20000,
        },
        {
          setting: "threshold_accelerometer",
          value: accelerometerData.threshold ? accelerometerData.threshold : 0,
        },
        {
          setting: "frequency_accelerometer_enforce",
          value: accelerometerData.enforce ? accelerometerData.enforce : false,
        },

        // barometer
        {
          setting: "status_barometer",
          value: sensorData.sensor_barometer
            ? sensorData.sensor_barometer
            : false,
        },
        {
          setting: "frequency_barometer",
          value: barometerData.frequency_sample_barometer
            ? barometerData.frequency_sample_barometer
            : 20000,
        },
        {
          setting: "threshold_barometer",
          value: barometerData.threshold ? barometerData.threshold : 0,
        },
        {
          setting: "frequency_barometer_enforce",
          value: barometerData.enforce ? barometerData.enforce : false,
        },

        // bluetooth
        {
          setting: "status_bluetooth",
          value: sensorData.sensor_bluetooth
            ? sensorData.sensor_bluetooth
            : false,
        },
        {
          setting: "frequency_bluetooth",
          value: bluetoothData.frequency_bluetooth
            ? bluetoothData.frequency_bluetooth
            : 60,
        },

        // gravity
        {
          setting: "status_gravity",
          value: sensorData.sensor_gravity ? sensorData.sensor_gravity : false,
        },
        {
          setting: "frequency_gravity",
          value: gravityData.frequency_gravity
            ? gravityData.frequency_gravity
            : 20000,
        },
        {
          setting: "threshold_gravity",
          value: gravityData.threshold ? gravityData.threshold : 0,
        },
        {
          setting: "frequency_gravity_enforce",
          value: gravityData.enforce ? gravityData.enforce : false,
        },

        // gyroscope
        {
          setting: "status_gyroscope",
          value: sensorData.sensor_gyroscope
            ? sensorData.sensor_gyroscope
            : false,
        },
        {
          setting: "frequency_gyroscope",
          value: gyroscopeData.frequency_gyroscope
            ? gyroscopeData.frequency_gyroscope
            : 20000,
        },
        {
          setting: "threshold_gyroscope",
          value: gyroscopeData.threshold ? gyroscopeData.threshold : 0,
        },
        {
          setting: "frequency_gyroscope_enforce",
          value: gyroscopeData.enforce ? gyroscopeData.enforce : false,
        },

        // light
        {
          setting: "status_light",
          value: sensorData.sensor_light ? sensorData.sensor_light : false,
        },
        {
          setting: "frequency_light",
          value: lightData.frequency_light ? lightData.frequency_light : 20000,
        },
        {
          setting: "threshold_light",
          value: lightData.threshold ? lightData.threshold : 0,
        },
        {
          setting: "frequency_light_enforce",
          value: lightData.enforce ? lightData.enforce : false,
        },

        // linear accelerometer
        {
          setting: "status_linear_accelerometer",
          value: sensorData.sensor_linear_accelerometer
            ? sensorData.sensor_linear_accelerometer
            : false,
        },
        {
          setting: "frequency_linear_accelerometer",
          value: linearAccelerometerData.frequency_linear_accelerometer
            ? linearAccelerometerData.frequency_linear_accelerometer
            : 20000,
        },
        {
          setting: "threshold_linear_accelerometer",
          value: linearAccelerometerData.threshold
            ? linearAccelerometerData.threshold
            : 0,
        },
        {
          setting: "frequency_linear_accelerometer_enforce",
          value: linearAccelerometerData.enforce
            ? linearAccelerometerData.enforce
            : false,
        },

        // location
        {
          setting: "location",
          value: sensorData.sensor_locations
            ? sensorData.sensor_locations
            : false,
        },
        {
          setting: "status_location_gps",
          value: locationsData.gps ? locationsData.gps : false,
        },
        {
          setting: "status_location_network",
          value: locationsData.network ? locationsData.network : false,
        },
        {
          setting: "frequency_location_gps",
          value: locationsData.frequency_gps
            ? locationsData.frequency_gps
            : 180,
        },
        {
          setting: "frequency_location_network",
          value: locationsData.frequency_network
            ? locationsData.frequency_network
            : 300,
        },
        {
          setting: "min_location_gps_accuracy",
          value: locationsData.min_gps_freq ? locationsData.min_gps_freq : 150,
        },
        {
          setting: "min_location_network_accuracy",
          value: locationsData.min_network_freq
            ? locationsData.min_network_freq
            : 1500,
        },
        {
          setting: "location_expiration_time",
          value: locationsData.expiration ? locationsData.expiration : 300,
        },
        {
          setting: "status_location_passive",
          value: locationsData.passive ? locationsData.passive : false,
        },
        {
          setting: "location_save_all",
          value: locationsData.save_all ? locationsData.save_all : false,
        },

        // magnetometer
        {
          setting: "status_magnetometer",
          value: sensorData.sensor_magnetometer
            ? sensorData.sensor_magnetometer
            : false,
        },
        {
          setting: "frequency_magnetometer",
          value: magnetometerData.frequency_magnetometer
            ? magnetometerData.frequency_magnetometer
            : 20000,
        },
        {
          setting: "threshold_magnetometer",
          value: magnetometerData.threshold ? magnetometerData.threshold : 0,
        },
        {
          setting: "frequency_magnetometer_enforce",
          value: magnetometerData.enforce ? magnetometerData.enforce : false,
        },

        // network
        {
          setting: "network",
          value: sensorData.sensor_network ? sensorData.sensor_network : false,
        },
        {
          setting: "status_network_events",
          value: networkData.events ? networkData.events : false,
        },
        {
          setting: "status_network_traffic",
          value: networkData.traffic ? networkData.traffic : false,
        },
        {
          setting: "frequency_network_traffic",
          value: networkData.frequency_network_traffic
            ? networkData.frequency_network_traffic
            : 30,
        },

        // processor
        {
          setting: "status_processor",
          value: sensorData.sensor_processor
            ? sensorData.sensor_processor
            : false,
        },
        {
          setting: "frequency_processor",
          value: processorData.frequency_processor
            ? processorData.frequency_processor
            : 10,
        },

        // proximity
        {
          setting: "status_proximity",
          value: sensorData.sensor_proximity
            ? sensorData.sensor_proximity
            : false,
        },
        {
          setting: "frequency_proximity",
          value: proximityData.frequency_proximity
            ? proximityData.frequency_proximity
            : 20000,
        },
        {
          setting: "threshold_proximity",
          value: proximityData.threshold ? proximityData.threshold : 0,
        },
        {
          setting: "frequency_proximity_enforce",
          value: proximityData.enforce ? proximityData.enforce : false,
        },

        // rotation
        {
          setting: "status_rotation",
          value: sensorData.sensor_rotation
            ? sensorData.sensor_rotation
            : false,
        },
        {
          setting: "frequency_rotation",
          value: rotationData.frequency_rotation
            ? rotationData.frequency_rotation
            : 20000,
        },
        {
          setting: "threshold_rotation",
          value: rotationData.threshold ? rotationData.threshold : 0,
        },
        {
          setting: "frequency_rotation_enforce",
          value: rotationData.enforce ? rotationData.enforce : false,
        },

        // temperature
        {
          setting: "status_temperature",
          value: sensorData.sensor_temperature
            ? sensorData.sensor_temperature
            : false,
        },
        {
          setting: "frequency_temperature",
          value: temperatureData.frequency_temperature
            ? temperatureData.frequency_temperature
            : 20000,
        },
        {
          setting: "threshold_temperature",
          value: temperatureData.threshold ? temperatureData.threshold : 0,
        },
        {
          setting: "frequency_temperature_enforce",
          value: temperatureData.enforce ? temperatureData.enforce : false,
        },

        // wifi
        {
          setting: "status_wifi",
          value: sensorData.sensor_wifi ? sensorData.sensor_wifi : false,
        },
        {
          setting: "frequency_wifi",
          value: wifiData.frequency_wifi ? wifiData.frequency_wifi : 60,
        },
        // screenshot
        {
          setting: "status_screenshot",
          value: sensorData.sensor_screenshot
            ? sensorData.sensor_screenshot
            : false,
        },
        {
          setting: "capture_time_interval",
          value: screenshotData.capture_time_interval
            ? screenshotData.capture_time_interval
            : 5,
        },
        {
          setting: "compress_rate",
          value: screenshotData.compress_rate
            ? screenshotData.compress_rate
            : 20,
        },
        {
          setting: "status_screenshot_local_storage",
          value: screenshotData.status_screenshot_local_storage
            ? screenshotData.status_screenshot_local_storage
            : false,
        },
        {
          setting: "screenshot_package_names",
          value: applicationSensor.screenshot_package_names
            ? applicationSensor.screenshot_package_names
            : "",
        },
        {
          setting: "screenshot_package_specification",
          value: applicationSensor.screenshot_package_specification
            ? applicationSensor.screenshot_package_specification
            : "2",
        },
        {
          setting: "status_notes",
          value: sensorData.sensor_notes ? sensorData.sensor_notes : false,
        },
        {
          setting: "status_plugin_ambient_noise",
          value: sensorData.status_plugin_ambient_noise
            ? sensorData.status_plugin_ambient_noise
            : false,
        },
        {
          setting: "frequency_plugin_ambient_noise",
          value: pluginData.frequency_plugin_ambient_noise
            ? pluginData.frequency_plugin_ambient_noise
            : 5,
        },
        {
          setting: "plugin_ambient_noise_sample_size",
          value: pluginData.plugin_ambient_noise_sample_size
            ? pluginData.plugin_ambient_noise_sample_size
            : 30,
        },
        {
          setting: "plugin_ambient_noise_silence_threshold",
          value: pluginData.plugin_ambient_noise_silence_threshold
            ? pluginData.plugin_ambient_noise_silence_threshold
            : 50,
        },
        {
          setting: "status_plugin_openweather",
          value: sensorData.status_plugin_openweather
            ? sensorData.status_plugin_openweather
            : false,
        },
        {
          setting: "plugin_openweather_frequency",
          value: pluginData.plugin_openweather_frequency
            ? pluginData.plugin_openweather_frequency
            : 30,
        },
        {
          setting: "plugin_openweather_api_key",
          value: pluginData.plugin_openweather_api_key
            ? pluginData.plugin_openweather_api_key
            : "",
        },
        {
          setting: "plugin_openweather_measurement_units",
          value: pluginData.plugin_openweather_measurement_units
            ? pluginData.plugin_openweather_measurement_units
            : "metric",
        },
        // plugin: google activity recognition
        {
          setting: "status_plugin_google_activity_recognition",
          value: sensorData.status_plugin_google_activity_recognition
            ? sensorData.status_plugin_google_activity_recognition
            : false,
        },
        {
          setting: "frequency_plugin_google_activity_recognition",
          value: pluginData.frequency_plugin_google_activity_recognition
            ? pluginData.frequency_plugin_google_activity_recognition
            : 10,
        },
        // plugin: esm scheduler
        {
          setting: "status_plugin_esm_scheduler",
          value: sensorData.status_plugin_esm_scheduler
            ? sensorData.status_plugin_esm_scheduler
            : false,
        },
        // plugin: fitbit
        {
          setting: "status_plugin_fitbit",
          value: sensorData.status_plugin_fitbit
            ? sensorData.status_plugin_fitbit
            : false,
        },
        {
          setting: "units_plugin_fitbit",
          value: pluginData.units_plugin_fitbit
            ? pluginData.units_plugin_fitbit
            : "metric",
        },
        {
          setting: "fitbit_granularity",
          value: pluginData.fitbit_granularity
            ? pluginData.fitbit_granularity
            : 15,
        },
        {
          setting: "fitbit_hr_granularity",
          value: pluginData.fitbit_hr_granularity
            ? pluginData.fitbit_hr_granularity
            : 1,
        },
        {
          setting: "plugin_fitbit_frequency",
          value: pluginData.plugin_fitbit_frequency
            ? pluginData.plugin_fitbit_frequency
            : 60,
        },
        {
          setting: "api_key_plugin_fitbit",
          value: pluginData.api_key_plugin_fitbit
            ? pluginData.api_key_plugin_fitbit
            : "",
        },
        {
          setting: "api_secret_plugin_fitbit",
          value: pluginData.api_secret_plugin_fitbit
            ? pluginData.api_secret_plugin_fitbit
            : "",
        },
        // plugin: contacts list
        {
          setting: "status_plugin_contacts",
          value: sensorData.status_plugin_contacts
            ? sensorData.status_plugin_contacts
            : false,
        },
        {
          setting: "frequency_plugin_contacts",
          value: pluginData.frequency_plugin_contacts
            ? pluginData.frequency_plugin_contacts
            : 30,
        },
        // plugin: google auth
        {
          setting: "status_plugin_google_login",
          value: sensorData.status_plugin_google_login
            ? sensorData.status_plugin_google_login
            : false,
        },
        // plugin: google fused location
        {
          setting: "status_google_fused_location",
          value: sensorData.status_google_fused_location
            ? sensorData.status_google_fused_location
            : false,
        },
        {
          setting: "frequency_google_fused_location",
          value: pluginData.frequency_google_fused_location
            ? pluginData.frequency_google_fused_location
            : 300,
        },
        {
          setting: "max_frequency_google_fused_location",
          value: pluginData.max_frequency_google_fused_location
            ? pluginData.max_frequency_google_fused_location
            : 60,
        },
        {
          setting: "fallback_location_timeout",
          value: pluginData.fallback_location_timeout
            ? pluginData.fallback_location_timeout
            : 20,
        },
        {
          setting: "accuracy_google_fused_location",
          value: normalizeFusedLocationAccuracy(
            pluginData.accuracy_google_fused_location
          ),
        },
        // plugin: device usage
        {
          setting: "status_plugin_device_usage",
          value: sensorData.status_plugin_device_usage
            ? sensorData.status_plugin_device_usage
            : false,
        },
        // plugin: conversations
        {
          setting: "status_plugin_studentlife_audio",
          value: sensorData.status_plugin_studentlife_audio
            ? sensorData.status_plugin_studentlife_audio
            : false,
        },
        {
          setting: "plugin_conversations_delay",
          value: pluginData.plugin_conversations_delay
            ? pluginData.plugin_conversations_delay
            : 5,
        },
        {
          setting: "plugin_conversations_off_duty",
          value: pluginData.plugin_conversations_off_duty
            ? pluginData.plugin_conversations_off_duty
            : 30,
        },
        {
          setting: "plugin_conversations_length",
          value: pluginData.plugin_conversations_length
            ? pluginData.plugin_conversations_length
            : 60,
        },
        // ambient noise: iOS no-raw flag
        {
          setting: "plugin_ambient_noise_no_raw",
          value: pluginData.plugin_ambient_noise_no_raw
            ? pluginData.plugin_ambient_noise_no_raw
            : false,
        },
        // significant motion (shared: controls both Android and iOS)
        {
          setting: "status_significant_motion",
          value:
            sensorData.ios_significant_motion !== undefined
              ? sensorData.ios_significant_motion
              : false,
        },
        // default sensors
        { setting: "status_esm", value: true },
        {
          setting: "status_webservice",
          value:
            sensorData.status_webservice !== undefined
              ? sensorData.status_webservice
              : true,
        },
      ],
      ios_sensors: {
        significant_motion:
          sensorData.ios_significant_motion !== undefined
            ? sensorData.ios_significant_motion
            : false,
        websocket:
          sensorData.ios_websocket !== undefined
            ? sensorData.ios_websocket
            : false,
        mqtt: mqttEnabled,
      },
      ios_plugins: {
        plugin_calendar: sensorData.status_plugin_calendar
          ? sensorData.status_plugin_calendar
          : false,
        plugin_esm_scheduler: sensorData.status_ios_esm_scheduler
          ? sensorData.status_ios_esm_scheduler
          : false,
        plugin_headphone_motion: sensorData.status_plugin_headphone_motion
          ? sensorData.status_plugin_headphone_motion
          : false,
        plugin_health_kit: sensorData.status_health_kit
          ? sensorData.status_health_kit
          : false,
        plugin_ble_heartrate: sensorData.status_plugin_ble_heartrate
          ? sensorData.status_plugin_ble_heartrate
          : false,
        plugin_ntptime: sensorData.status_plugin_ntptime
          ? sensorData.status_plugin_ntptime
          : false,
        plugin_ios_pedometer: sensorData.status_plugin_ios_pedometer
          ? sensorData.status_plugin_ios_pedometer
          : false,
        plugin_push_notification: sensorData.status_push_notication
          ? sensorData.status_push_notication
          : false,
      },
      ios_plugin_settings: {
        frequency_health_kit: pluginData.frequency_health_kit
          ? pluginData.frequency_health_kit
          : 30,
        preperiod_days_health_kit: pluginData.preperiod_days_health_kit
          ? pluginData.preperiod_days_health_kit
          : 7,
        plugin_ble_heartrate_interval_min:
          pluginData.plugin_ble_heartrate_interval_min
            ? pluginData.plugin_ble_heartrate_interval_min
            : 1,
        plugin_ble_heartrate_active_time_sec:
          pluginData.plugin_ble_heartrate_active_time_sec
            ? pluginData.plugin_ble_heartrate_active_time_sec
            : 30,
        frequency_ios_pedometer: pluginData.frequency_ios_pedometer
          ? pluginData.frequency_ios_pedometer
          : 30,
        preperiod_days_ios_pedometer: pluginData.preperiod_days_ios_pedometer
          ? pluginData.preperiod_days_ios_pedometer
          : 7,
        plugin_push_notification_server:
          pluginData.plugin_push_notification_server
            ? pluginData.plugin_push_notification_server
            : "",
      },
    };
  }

  const [open, setOpen] = React.useState(false);

  const validationOn = () => {
    setOpen(true);
  };

  const validationClose = () => {
    setOpen(false);
    // eslint-disable-next-line no-use-before-define
    setBlankFields((oldArray) => []);
  };

  const [blankFields, setBlankFields] = React.useState([]);

  const updateBlankFields = (name) => {
    setBlankFields((oldArray) => [...oldArray, name]);
  };

  const [validation, setValidation] = React.useState(true);

  // const validate = (fieldName, value) => {
  //   setValidation({
  //     ...validation,
  //     [fieldName]: value,
  //   });
  // };
  const validate = (value) => {
    setValidation(value);
  };

  // eslint-disable-next-line react/no-unstable-nested-components
  function AlertDialog() {
    // console.log(blankFields);
    return (
      <div>
        <Dialog
          open={open}
          onClose={validationClose}
          aria-labelledby="alert-dialog-title"
          aria-describedby="alert-dialog-description"
        >
          <DialogTitle id="alert-dialog-title">
            Required fields are left blank.
          </DialogTitle>
          <DialogContent>
            <DialogContentText id="alert-dialog-description">
              The following pages need to be rechecked:{"\n"}
              {/* {blankFields} */}
              {blankFields.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={validationClose} autoFocus>
              Okay
            </Button>
            {/* <Button autoFocus>Okay</Button> */}
          </DialogActions>
        </Dialog>
      </div>
    );
  }

  function saveJsonFile() {
    return Axios({
      method: "post",
      url: "save_json_file/",
      data: {
        text: JSON.stringify(buildResult()),
      },
    });
  }

  return (
    <ThemeProvider theme={customisedTheme}>
      <div>
        <div className="main_vertical_layout">
          <div className="border">
            <Grid width={250} ml={5} mt={3}>
              <p className="title">Study Information</p>
            </Grid>

            {displayInfo(`Study title`, studyInformation.study_title)}
            {displayInfo(
              `Study description`,
              studyInformation.study_description
            )}

            <Grid
              container
              justifyContent="flex-end"
              marginBottom={3}
              marginRight={2}
            >
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/study_information");
                }}
              >
                EDIT STUDY INFORMATION
              </Button>
            </Grid>
          </div>
          <div className="border">
            <Grid width={250} ml={5} mt={3}>
              <p className="title">Questions</p>
            </Grid>

            {questionList}

            <Grid
              container
              justifyContent="flex-end"
              marginBottom={3}
              marginRight={2}
            >
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/questions");
                }}
              >
                EDIT QUESTIONS
              </Button>
            </Grid>
          </div>

          <div className="border">
            <Grid width={250} ml={5} mt={3}>
              <p className="title">Schedule configuration</p>
            </Grid>
            {/* {scheduleList} */}
            {schedules ? scheduleList : <div />}

            <Grid
              container
              justifyContent="flex-end"
              marginBottom={3}
              marginRight={2}
            >
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/schedule_configuration");
                }}
              >
                EDIT SCHEDULE CONFIGURATION
              </Button>
            </Grid>
          </div>
          <div className="border">
            <Grid width={250} ml={5} mt={3}>
              <p className="title">Sensor data</p>
            </Grid>

            <Grid width={250} ml={5} mt={3}>
              <p className="title">Shared sensors</p>
            </Grid>
            {displaySensors("sensor_accelerometer", "Accelerometer")}
            {displaySensors("sensor_gyroscope", "Gyroscope")}
            {displaySensors("sensor_magnetometer", "Magnetometer")}
            {displaySensors("sensor_rotation", "Rotation")}
            {displaySensors(
              "sensor_linear_accelerometer",
              "Linear accelerometer"
            )}
            {displaySensors("sensor_barometer", "Barometer")}
            {displaySensors("sensor_battery", "Battery")}
            {displaySensors("sensor_bluetooth", "Bluetooth")}
            {displaySensors("sensor_wifi", "Wifi")}
            {displaySensors("sensor_screen", "Screen")}
            {displaySensors("sensor_locations", "Locations")}
            {displaySensors("sensor_processor", "Processor")}
            {displaySensors("sensor_timezone", "Timezone")}
            {displaySensors("ios_significant_motion", "Significant Motion")}
            {displaySensors("sensor_network", "Network")}
            {displaySensors("sensor_communication", "Communication (Calls)")}

            <Grid width={250} ml={5} mt={3}>
              <p className="title">Shared plugins</p>
            </Grid>
            {displaySensors("status_plugin_ambient_noise", "Ambient Noise")}
            {displaySensors("status_plugin_openweather", "OpenWeather")}

            <Grid width={250} ml={5} mt={3}>
              <p className="title">Android-only sensors</p>
            </Grid>
            {displaySensors("sensor_gravity", "Gravity")}
            {displaySensors("sensor_light", "Light")}
            {displaySensors("sensor_proximity", "Proximity")}
            {displaySensors("sensor_temperature", "Temperature")}
            {displaySensors("sensor_application", "Applications")}
            {displaySensors("sensor_installation", "Installation")}
            {displaySensors("sensor_telephony", "Telephony")}
            {displaySensors("sensor_screenshot", "Screenshot")}
            {displaySensors("sensor_notes", "Notes")}
            {displaySensors("status_plugin_esm_scheduler", "ESM Scheduler")}
            {displaySensors("status_mqtt", "MQTT")}

            <Grid width={250} ml={5} mt={3}>
              <p className="title">iOS-only sensors</p>
            </Grid>
            {displaySensors(
              "status_plugin_google_activity_recognition",
              "Activity Recognition"
            )}
            {displaySensors("status_plugin_fitbit", "Fitbit")}
            {displaySensors("status_plugin_contacts", "Contacts")}
            {displaySensors("status_plugin_google_login", "Google Login")}
            {displaySensors("status_google_fused_location", "Fused Location")}
            {displaySensors("status_plugin_device_usage", "Device Usage")}
            {displaySensors("status_plugin_studentlife_audio", "Conversation")}
            {displaySensors("status_plugin_calendar", "Calendar")}
            {displaySensors(
              "status_plugin_headphone_motion",
              "Headphone Motion"
            )}
            {displaySensors("status_health_kit", "HealthKit")}
            {displaySensors("status_plugin_ble_heartrate", "Heart Rate (BLE)")}
            {displaySensors("status_plugin_ntptime", "NTP")}
            {displaySensors("status_plugin_ios_pedometer", "Pedometer")}
            {displaySensors("status_push_notication", "Push Notification")}

            <Grid
              container
              justifyContent="flex-end"
              marginBottom={3}
              marginRight={2}
            >
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/sensor_data");
                }}
              >
                EDIT SENSOR DATA
              </Button>
            </Grid>
          </div>

          <Box sx={{ width: "100%" }} mt={5} marginBottom={5}>
            <Grid
              container
              rowSpacing={1}
              columnSpacing={{ xs: 1, sm: 2, md: 23 }}
            >
              <Grid xs />
              <Grid>
                <p style={{ color: "#0f172a", fontWeight: "bold" }}>
                  Update shared configuration
                </p>
                <p style={{ color: "#475569", maxWidth: "680px" }}>
                  Saving here updates the shared study source and regenerates
                  the Android and iOS configuration files used by this
                  deployment. Participants keep using the same public study
                  links.
                </p>
                {saveState.status !== "idle" && (
                  <Alert
                    severity={
                      saveState.status === "success" ? "success" : "error"
                    }
                    sx={{ mt: 2, maxWidth: "680px" }}
                  >
                    <AlertTitle>
                      {saveState.status === "success"
                        ? "Configuration updated"
                        : "Update failed"}
                    </AlertTitle>
                    {saveState.message}
                  </Alert>
                )}
              </Grid>
              <Grid xs={12} md="auto">
                <div className="overview-actions">
                  <Button
                    color="main"
                    variant="contained"
                    onClick={async () => {
                      setSaveState({
                        status: "idle",
                        message: "",
                      });
                      setBlankFields([]);
                      validationOn();

                      const validility =
                        checkStudyInformationValidation() &&
                        checkQuestionValidation() &&
                        checkScheduleValidation();

                      validate(validility);

                      if (!checkStudyInformationValidation()) {
                        updateBlankFields("Study information page");
                      }
                      if (!checkQuestionValidation()) {
                        updateBlankFields("Question page");
                      }
                      if (!checkScheduleValidation()) {
                        updateBlankFields("Schedule page");
                      }

                      if (validility) {
                        try {
                          validationClose();
                          await saveJsonFile();
                          setSaveState({
                            status: "success",
                            message:
                              "The shared study configuration was updated successfully.",
                          });
                        } catch (error) {
                          setSaveState({
                            status: "error",
                            message:
                              error?.response?.data?.msg ||
                              error.message ||
                              "The configuration could not be updated.",
                          });
                        }
                      }
                    }}
                  >
                    UPDATE CONFIGURATION
                  </Button>
                  <Button
                    color="main"
                    variant="outlined"
                    onClick={() => {
                      window.location.assign("/studies/");
                    }}
                  >
                    OPEN STUDIES
                  </Button>
                  <Button
                    color="main"
                    variant="outlined"
                    onClick={() => {
                      window.location.assign("/");
                    }}
                  >
                    MAIN PAGE
                  </Button>
                </div>
                {!validation ? AlertDialog() : <div />}
              </Grid>
            </Grid>
          </Box>
        </div>
      </div>
    </ThemeProvider>
  );
}
