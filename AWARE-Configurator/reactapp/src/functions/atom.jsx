import { atom } from "recoil";

const localStorageEffect =
  (storageKey) =>
  ({ setSelf, onSet }) => {
    if (typeof window === "undefined") {
      return;
    }

    const savedValue = window.localStorage.getItem(storageKey);
    if (savedValue != null) {
      try {
        setSelf(JSON.parse(savedValue));
      } catch (error) {
        window.localStorage.removeItem(storageKey);
      }
    }

    onSet((newValue, _, isReset) => {
      if (isReset) {
        window.localStorage.removeItem(storageKey);
        return;
      }
      window.localStorage.setItem(storageKey, JSON.stringify(newValue));
    });
  };

export const isLoadingState = atom({
  key: "isLoadingState",
  default: false,
});

export const studyFormStudyInformationState = atom({
  key: "studyFormStudyInformationState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("studyFormStudyInformationState")],
});

// database connection
export const databaseConnectionState = atom({
  key: "databaseConnectionState",
  default: false,
  effects_UNSTABLE: [localStorageEffect("databaseConnectionState")],
});

// questions
export const studyFormQuestionsState = atom({
  key: "studyFormQuestionsState",
  default: [{}],
  effects_UNSTABLE: [localStorageEffect("studyFormQuestionsState")],
});

export const studyFormScheduleConfigurationState = atom({
  key: "studyFormScheduleConfigurationState",
  default: [{}],
  effects_UNSTABLE: [localStorageEffect("studyFormScheduleConfigurationState")],
});

export const studyFormSensorDataState = atom({
  key: "studyFormSensorDataState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("studyFormSensorDataState")],
});

export const sensorDataState = atom({
  key: "sensorDataState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("sensorDataState")],
});

export const databaseInformationState = atom({
  key: "databaseDataState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("databaseDataState")],
});

// Software Sensor SubFields:

export const applicationSensorState = atom({
  key: "applicationSensorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("applicationSensorState")],
});

export const communicationSensorState = atom({
  key: "communicationSensorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("communicationSensorState")],
});

export const screenSensorState = atom({
  key: "screenSensorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("screenSensorState")],
});
export const timezoneState = atom({
  key: "timezoneState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("timezoneState")],
});

export const screenshotSensorState = atom({
  key: "screenshotSensorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("screenshotSensorState")],
});

export const noteState = atom({
  key: "noteState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("noteState")],
});

export const pluginSensorState = atom({
  key: "pluginSensorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("pluginSensorState")],
});

// Hardware Sensor SubFields:

export const accelerometerState = atom({
  key: "accelerometerState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("accelerometerState")],
});

export const barometerState = atom({
  key: "barometerState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("barometerState")],
});

export const bluetoothState = atom({
  key: "bluetoothState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("bluetoothState")],
});

export const gravityState = atom({
  key: "gravityState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("gravityState")],
});

export const gyroscopeState = atom({
  key: "gyroscopeState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("gyroscopeState")],
});

export const lightState = atom({
  key: "lightState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("lightState")],
});

export const linearAccelerometerState = atom({
  key: "linearAccelerometerState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("linearAccelerometerState")],
});

export const locationsState = atom({
  key: "locationsState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("locationsState")],
});

export const magnetometerState = atom({
  key: "magnetometerState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("magnetometerState")],
});

export const networkState = atom({
  key: "networkState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("networkState")],
});

export const processorState = atom({
  key: "processorState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("processorState")],
});

export const proximityState = atom({
  key: "proximityState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("proximityState")],
});

export const rotationState = atom({
  key: "rotationState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("rotationState")],
});

export const temperatureState = atom({
  key: "temperatureState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("temperatureState")],
});

export const wifiState = atom({
  key: "wifiState",
  default: {},
  effects_UNSTABLE: [localStorageEffect("wifiState")],
});

export const studyIdState = atom({
  key: "studyIdState",
  default: "",
  effects_UNSTABLE: [localStorageEffect("studyIdState")],
});

export const createTimeState = atom({
  key: "createTimeState",
  default: "",
  effects_UNSTABLE: [localStorageEffect("createTimeState")],
});

export const dialogState = atom({
  key: "dialogState",
  default: { isOpen: false, title: "", content: "" },
});
