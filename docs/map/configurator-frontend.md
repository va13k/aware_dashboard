# Configurator: the front end

The form a researcher fills in. React with Recoil, built by
`react-scripts` and served as static files by the Django half. Node 18.
Prose: [`AWARE-Configurator/README.md`](../../AWARE-Configurator/README.md).

The base path is baked in at image build time as `PUBLIC_URL=/configurator`, so
changing it needs a rebuild rather than a restart.

---

## What owns what

Paths are under [`AWARE-Configurator/reactapp/src/`](../../AWARE-Configurator/reactapp/src).

| Concept | File |
| --- | --- |
| Every Recoil atom | [`functions/atom.jsx`](../../AWARE-Configurator/reactapp/src/functions/atom.jsx) |
| Loading a study config into the atoms | [`pages/Upload.jsx`](../../AWARE-Configurator/reactapp/src/pages/Upload.jsx) |
| Every sensor's UI | [`pages/SensorData.jsx`](../../AWARE-Configurator/reactapp/src/pages/SensorData.jsx) |
| Assembling the config and posting it | [`pages/Overview.jsx`](../../AWARE-Configurator/reactapp/src/pages/Overview.jsx) |
| Study title, contact, and the ingest password field | [`pages/StudyInformation.jsx`](../../AWARE-Configurator/reactapp/src/pages/StudyInformation.jsx) |
| ESM questions and their schedules | [`pages/StudyQuestions.jsx`](../../AWARE-Configurator/reactapp/src/pages/StudyQuestions.jsx), [`pages/ScheduleConfiguration.jsx`](../../AWARE-Configurator/reactapp/src/pages/ScheduleConfiguration.jsx) |
| Routing one control's changes to the right atom | [`components/SensorComponent/SensorComponent.jsx`](../../AWARE-Configurator/reactapp/src/components/SensorComponent/SensorComponent.jsx) |
| The Android config template the form starts from | [`reactapp/public/study-config.json`](../../AWARE-Configurator/reactapp/public/study-config.json) |
| The sensor catalogue and threshold presets | [`functions/sensorCatalogue.js`](../../AWARE-Configurator/reactapp/src/functions/sensorCatalogue.js), [`functions/thresholdPresets.js`](../../AWARE-Configurator/reactapp/src/functions/thresholdPresets.js) |

---

## How a control reaches an atom

`sensorDataState` holds the top-level on/off booleans, one per sensor. Each sensor's
sub-settings live in an atom of their own, `accelerometerState` and the rest.

A control does not know which atom it writes. `SensorComponent` routes by its
`modeState` prop: `"sensor"` goes to `sensorDataState`, and any other value names
the sensor whose own atom takes the write.

---

## Adding a sensor setting touches four places

Miss one and the setting is silently dropped rather than reported.

1. **`study-config.json`** gains the entry, or the form starts without it.
2. **`Upload.jsx`** gains a `case` in `readJsonObject` and the setter call, or a
   saved study loads without the value.
3. **`SensorData.jsx`** gains the control.
4. **`Overview.jsx`** gains the entry in the `sensors[]` array it posts, or the
   value never leaves the browser.

Then [`shared_config/serializers.py`](../../shared_config/serializers.py) if the
setting has to reach iOS. See [shared_config](shared-config.md).

The field names have to match across all four. Magnetometer's sub-settings are
`.threshold` and `.enforce`, not `threshold_magnetometer`.

---

## Traps

- **A frequency of `0` does not save; a threshold of `0` does.** Both fields share
  the guard in
  [`FrequencyField.jsx`](../../AWARE-Configurator/reactapp/src/components/FrequencyField/FrequencyField.jsx),
  which accepts zero only when `allowZero` is set, and
  [`ThresholdField.jsx`](../../AWARE-Configurator/reactapp/src/components/ThresholdField/ThresholdField.jsx)
  is the only caller that sets it.
- **`displaySensors` in `Overview.jsx` tests the value, not the key.** A sensor
  present but `false` renders nothing, which is what it should do.
- **The browser holds its own copy of the config it round-trips.** The dataflow it
  submits is therefore ignored, so a stale tab cannot re-address a running study.

---

## Tests

```bash
cd AWARE-Configurator/reactapp && npx react-scripts test --watchAll=false
```

Two test files, over the threshold presets and the threshold field. The pages
themselves are not covered.
