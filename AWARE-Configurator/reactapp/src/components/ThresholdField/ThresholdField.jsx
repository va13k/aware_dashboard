import React from "react";
import FrequencyField from "../FrequencyField/FrequencyField";
import {
  THRESHOLDS,
  thresholdDescription,
} from "../../functions/thresholdPresets";

// One threshold control per sensor, built from the sensor's entry in
// THRESHOLDS. The unit, presets, recommended limit and explanation all come
// from that one table, so the ten threshold fields cannot drift apart in
// wording or in the values they offer.
function ThresholdField(inputs) {
  const { sensor, studyField } = inputs;
  const spec = THRESHOLDS[sensor];
  if (!spec) return null;

  return (
    <FrequencyField
      id={`threshold_${sensor}`}
      title={`Threshold ${spec.label}`}
      inputLabel={`threshold in ${spec.unit}`}
      defaultNum={0}
      description={thresholdDescription(sensor)}
      field="threshold"
      studyField={studyField}
      modeState={sensor}
      presets={spec.presets}
      warnAbove={spec.warnAbove}
      allowZero
    />
  );
}

export default ThresholdField;
