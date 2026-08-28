import React from "react";
import PropTypes from "prop-types";
import Tooltip from "@mui/material/Tooltip";
import TuneIcon from "@mui/icons-material/Tune";
import AndroidIcon from "@mui/icons-material/Android";
import AppleIcon from "@mui/icons-material/Apple";
import { SENSOR_ICONS } from "../../functions/sensorCatalogue";
import "./SensorCard.css";

/**
 * One sensor, as a card that shows whether it is being collected.
 *
 * Colour carries the state and nothing else does: a card is a way in, not a
 * control, so the only thing a click can do is open the sensor and let the
 * decision be made where its settings and its description are.
 */
export default function SensorCard({ sensor, enabled, onOpen }) {
  const Icon = SENSOR_ICONS[sensor.icon];
  const both = sensor.platform === "both";
  const on = Boolean(enabled);

  return (
    <div
      role="button"
      tabIndex={0}
      className={on ? "sensor_card on" : "sensor_card"}
      onClick={() => onOpen(sensor)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(sensor);
        }
      }}
    >
      <Icon sx={{ fontSize: 30, color: on ? "#1FB3DF" : "#8A9199" }} />

      <span className="sensor_card_name">{sensor.name}</span>

      <div className="sensor_card_platforms">
        {both || sensor.platform === "android" ? (
          <AndroidIcon sx={{ fontSize: 13 }} />
        ) : null}
        {both || sensor.platform === "ios" ? (
          <AppleIcon sx={{ fontSize: 13 }} />
        ) : null}
        {sensor.settings ? (
          <Tooltip title="Has its own settings">
            <TuneIcon sx={{ fontSize: 13 }} />
          </Tooltip>
        ) : null}
      </div>
    </div>
  );
}

SensorCard.propTypes = {
  sensor: PropTypes.shape({
    name: PropTypes.string.isRequired,
    icon: PropTypes.string.isRequired,
    platform: PropTypes.string.isRequired,
    settings: PropTypes.string,
  }).isRequired,
  enabled: PropTypes.bool,
  onOpen: PropTypes.func.isRequired,
};

SensorCard.defaultProps = { enabled: false };
