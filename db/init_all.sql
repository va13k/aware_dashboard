-- GENERATED FILE - DO NOT EDIT.
-- Built by db/build_init_all.py from 00-bootstrap.sql, android-tables.sql
-- and ios-tables.sql. Edit those and re-run the script.

CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

-- The participant passwords below are only a first-boot seed: on a fresh data
-- directory zz-participant-password.sh replaces them with the per-deployment
-- password generated into .env. CREATE USER IF NOT EXISTS means replaying this
-- file on later restarts never resets that password.
CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_analytics'@'%' IDENTIFIED BY 'analyticspass';
GRANT SELECT ON aware_android.* TO 'aware_analytics'@'%';
GRANT SELECT ON aware_ios.*     TO 'aware_analytics'@'%';

FLUSH PRIVILEGES;

USE `aware_android`;

CREATE TABLE IF NOT EXISTS `accelerometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `applications_crashes` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `application_name` text,
  `application_version` double DEFAULT '0',
  `error_short` text,
  `error_long` text,
  `error_condition` int DEFAULT '0',
  `is_system_app` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `applications_foreground` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `application_name` text,
  `is_system_app` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `applications_history` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `application_name` text,
  `process_importance` int DEFAULT '0',
  `process_id` int DEFAULT '0',
  `double_end_timestamp` double DEFAULT '1',
  `is_system_app` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `applications_notifications` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `application_name` text,
  `text` text,
  `sound` text,
  `vibrate` text,
  `defaults` int DEFAULT '-1',
  `flags` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `aware_device` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `board` text,
  `device` text,
  `build_id` text,
  `hardware` text,
  `manufacturer` text,
  `model` text,
  `product` text,
  `release` text,
  `sdk` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`),
  -- Intentionally non-unique: the client inserts a new row for each change.
  KEY `device_time` (`device_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `aware_log` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `log_type` varchar(32) DEFAULT '',
  `log_message` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`),
  KEY `log_type_time` (`log_type`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `aware_studies` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `study_url` text,
  `study_key` int DEFAULT '-1',
  `study_api` text,
  `study_pi` text,
  `study_config` text,
  `study_title` text,
  `study_description` text,
  `double_join` double DEFAULT '0',
  `double_updated` double DEFAULT '0',
  `double_exit` double DEFAULT '0',
  `study_compliance` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`),
  KEY `device_study_time` (`device_id`,`timestamp`,`_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `barometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `battery` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `battery_status` int DEFAULT '0',
  `battery_level` int DEFAULT '0',
  `battery_scale` int DEFAULT '0',
  `battery_voltage` int DEFAULT '0',
  `battery_temperature` int DEFAULT '0',
  `battery_adaptor` int DEFAULT '0',
  `battery_health` int DEFAULT '0',
  `battery_technology` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `battery_charges` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `battery_start` int DEFAULT '0',
  `battery_end` int DEFAULT '0',
  `double_end_timestamp` double DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `battery_discharges` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `battery_start` int DEFAULT '0',
  `battery_end` int DEFAULT '0',
  `double_end_timestamp` double DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `bluetooth` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `bt_address` varchar(150) DEFAULT '',
  `bt_name` text,
  `bt_rssi` int DEFAULT '0',
  `bt_status` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `calls` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `call_type` int DEFAULT '0',
  `call_duration` int DEFAULT '0',
  `trace` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `cdma` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `base_station_id` int DEFAULT '0',
  `double_base_station_latitude` double DEFAULT '0',
  `double_base_station_longitude` double DEFAULT '0',
  `network_id` int DEFAULT '0',
  `system_id` int DEFAULT '0',
  `signal_strength` int DEFAULT '-1',
  `cdma_ecio` int DEFAULT '-1',
  `evdo_dbm` int DEFAULT '-1',
  `evdo_ecio` int DEFAULT '-1',
  `evdo_snr` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `esms` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `esm_json` text,
  `esm_status` int DEFAULT '0',
  `esm_expiration_threshold` int DEFAULT '0',
  `esm_notification_timeout` int DEFAULT '0',
  `double_esm_user_answer_timestamp` double DEFAULT '0',
  `esm_user_answer` text,
  `esm_trigger` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `gravity` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `gsm` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `cid` int DEFAULT '-1',
  `lac` int DEFAULT '-1',
  `psc` int DEFAULT '0',
  `signal_strength` int DEFAULT '-1',
  `bit_error_rate` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `gsm_neighbor` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `cid` int DEFAULT '-1',
  `lac` int DEFAULT '-1',
  `psc` int DEFAULT '-1',
  `signal_strength` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `gyroscope` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `installations` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `application_name` text,
  `installation_status` int DEFAULT '-1',
  `version_name` text,
  `version_code` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `keyboard` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `package_name` text,
  `before_text` text,
  `current_text` text,
  `is_password` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `light` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_light_lux` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `linear_accelerometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `locations` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_latitude` double DEFAULT '0',
  `double_longitude` double DEFAULT '0',
  `double_bearing` double DEFAULT '0',
  `double_speed` double DEFAULT '0',
  `double_altitude` double DEFAULT '0',
  `provider` text,
  `accuracy` double DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `magnetometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `messages` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `message_type` int DEFAULT '0',
  `trace` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `mqtt_messages` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `topic` text,
  `message` text,
  `status` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `mqtt_subscriptions` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `topic` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `network` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `network_type` int DEFAULT '0',
  `network_subtype` text,
  `network_state` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `network_traffic` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `network_type` int DEFAULT '0',
  `double_received_bytes` double DEFAULT '0',
  `double_sent_bytes` double DEFAULT '0',
  `double_received_packets` double DEFAULT '0',
  `double_sent_packets` double DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `plugin_ambient_noise` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_frequency` double DEFAULT '0',
  `double_decibels` double DEFAULT '0',
  `double_rms` double DEFAULT '0',
  `is_silent` int DEFAULT '0',
  `double_silence_threshold` double DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `plugin_openweather` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `city` text,
  `temperature` double DEFAULT '0',
  `temperature_max` double DEFAULT '0',
  `temperature_min` double DEFAULT '0',
  `unit` text,
  `humidity` double DEFAULT '0',
  `pressure` double DEFAULT '0',
  `wind_speed` double DEFAULT '0',
  `wind_degrees` double DEFAULT '0',
  `cloudiness` double DEFAULT '0',
  `rain` double DEFAULT '0',
  `snow` double DEFAULT '0',
  `sunrise` double DEFAULT '0',
  `sunset` double DEFAULT '0',
  `weather_icon_id` int DEFAULT '0',
  `weather_description` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `proximity` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_proximity` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `rotation` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_values_0` double DEFAULT '0',
  `double_values_1` double DEFAULT '0',
  `double_values_2` double DEFAULT '0',
  `double_values_3` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `screen` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `screen_status` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_accelerometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_barometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_bluetooth` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `bt_address` varchar(150) DEFAULT '',
  `bt_name` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_gravity` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_gyroscope` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_light` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_linear_accelerometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_magnetometer` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_proximity` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_rotation` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_temperature` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_sensor_maximum_range` double DEFAULT '0',
  `double_sensor_minimum_delay` double DEFAULT '0',
  `sensor_name` text,
  `double_sensor_power_ma` double DEFAULT '0',
  `double_sensor_resolution` double DEFAULT '0',
  `sensor_type` text,
  `sensor_vendor` text,
  `sensor_version` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `sensor_wifi` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `mac_address` text,
  `ssid` text,
  `bssid` varchar(255) DEFAULT '',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `significant` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `is_moving` int DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `telephony` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `data_enabled` int DEFAULT '0',
  `imei_meid_esn` text,
  `software_version` text,
  `line_number` text,
  `network_country_iso_mcc` text,
  `network_operator_code` text,
  `network_operator_name` text,
  `network_type` int DEFAULT '0',
  `phone_type` int DEFAULT '0',
  `sim_state` int DEFAULT '0',
  `sim_operator_code` text,
  `sim_operator_name` text,
  `sim_serial` text,
  `subscriber_id` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `temperature` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `temperature_celsius` double DEFAULT '0',
  `accuracy` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `timezone` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `timezone` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `touch` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `touch_app` text,
  `touch_action` text,
  `touch_action_text` text,
  `scroll_items` int DEFAULT '-1',
  `scroll_from_index` int DEFAULT '-1',
  `scroll_to_index` int DEFAULT '-1',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `wifi` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `bssid` varchar(255) DEFAULT '',
  `ssid` text,
  `security` text,
  `frequency` int DEFAULT '0',
  `rssi` int DEFAULT '0',
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `screentext` (
    `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `timestamp` double DEFAULT '0',
    `device_id` varchar(150) DEFAULT '',
    `class_name` varchar(150) DEFAULT '',
    `package_name` varchar(150) DEFAULT '',
    `text` longtext,
    `user_action` int DEFAULT '0',
    `event_type` int DEFAULT '0',
    PRIMARY KEY (`_id`),
    KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `screenshot` (
     `_id` bigint NOT NULL AUTO_INCREMENT,
    `timestamp` double DEFAULT '0',
    `device_id` varchar(150) DEFAULT '',
    `package_name` text,
    `application_name` text,
    `image_data` longblob,
    PRIMARY KEY (`_id`),
    KEY `time_device` (`timestamp`, `device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `notes` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `note` text, 
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Declared by the Android client (Processor_Provider, Scheduler_Provider) but
-- absent from this schema until 2026-07-30. A table the client writes and the
-- server lacks makes every insert for it fail with no error surfaced on the
-- device, which is how `bluetooth` lost 2447 rows to a missing `bt_status`.
CREATE TABLE IF NOT EXISTS `processor` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `double_last_user` double DEFAULT '0',
  `double_last_system` double DEFAULT '0',
  `double_last_idle` double DEFAULT '0',
  `double_user_load` double DEFAULT '0',
  `double_system_load` double DEFAULT '0',
  `double_idle_load` double DEFAULT '0',
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `scheduler` (
  `_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `timestamp` double DEFAULT '0',
  `device_id` varchar(150) DEFAULT '',
  `schedule_id` text,
  `schedule` text,
  `last_triggered` double DEFAULT '0',
  `package_name` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

USE `aware_ios`;

-- Core sensors
CREATE TABLE IF NOT EXISTS `accelerometer` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `barometer` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `battery` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `battery_charges` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `battery_discharges` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `bluetooth` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `calls` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `esm` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `gyroscope` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `linear_accelerometer` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `locations` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `magnetometer` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `network` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `processor` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `rotation` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `screen` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `significant_motion` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `sensor_wifi` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `wifi` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `timezone` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- System / device tables
CREATE TABLE IF NOT EXISTS `aware_device` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
GRANT SELECT, UPDATE ON aware_ios.aware_device TO 'aware_ios_participant'@'%';
CREATE TABLE IF NOT EXISTS `aware_debug` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `basic_settings` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `labels` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `labels_boolean` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `labels_text` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `push_notification` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- Client logs
CREATE TABLE IF NOT EXISTS `ios_aware_log` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `ios_status_monitor` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- Location extras
CREATE TABLE IF NOT EXISTS `google_fused_location` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `ios_location_visit` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- Plugins
CREATE TABLE IF NOT EXISTS `plugin_ambient_noise` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_ble_heartrate` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_calendar` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_calendar_esm_scheduler` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_contacts` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_device_usage` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_fitbit` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `fitbit_data` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `fitbit_device` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_headphone_motion` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_ios_activity_recognition` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_ios_esm` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_ios_pedometer` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_ntptime` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_openweather` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `plugin_studentlife_audio` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- HealthKit
CREATE TABLE IF NOT EXISTS `health_kit` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `health_kit_category` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `health_kit_quantity` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));
CREATE TABLE IF NOT EXISTS `health_kit_workout` (`_id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, `timestamp` DOUBLE NOT NULL, `device_id` VARCHAR(128) NOT NULL, `data` JSON NOT NULL, INDEX `timestamp_device` (`timestamp`, `device_id`));

-- Dashboard-owned cache of exact per-(sensor, device) record counts.
--
-- Live COUNT(*) is O(rows) and the device page / manifest need dozens per
-- request, so counts are cached here and refreshed incrementally off the
-- request path (see analytics_api/app/services/record_counts.py): each refresh
-- scans only rows added since the per-sensor `_id` watermark. The table is
-- created here as root; the otherwise read-only `aware_analytics` user is
-- granted write on *only* this table so the API can maintain it without any
-- access to the AWARE data tables.
--
-- One copy lives in each platform database, alongside the source tables it
-- summarises, so a refresh reads and writes within a single connection.
--
-- This file is part of init_all.sql, which MySQL runs via --init-file on every
-- startup, so everything here is idempotent: fresh servers get the full schema
-- from the CREATE, and existing servers pick up later columns from the guarded
-- ALTER blocks (MySQL 8.0 has no `ADD COLUMN IF NOT EXISTS`).

-- `last_ts` (added after the initial release) is the newest row's `timestamp`
-- per (sensor, device), so the device page reads last-seen from the cache
-- instead of an `ORDER BY timestamp` scan per sensor.

USE `aware_android`;

CREATE TABLE IF NOT EXISTS `record_counts` (
  `sensor`     varchar(64)     NOT NULL,
  `device_id`  varchar(150)    NOT NULL,
  `count`      bigint unsigned NOT NULL DEFAULT 0,
  `last_id`    bigint unsigned NOT NULL DEFAULT 0,
  `last_ts`    double          NOT NULL DEFAULT 0,
  `updated_at` timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`sensor`, `device_id`),
  KEY `sensor_idx` (`sensor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @ddl := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = 'aware_android' AND TABLE_NAME = 'record_counts'
       AND COLUMN_NAME = 'last_ts') = 0,
  'ALTER TABLE `aware_android`.`record_counts` ADD COLUMN `last_ts` double NOT NULL DEFAULT 0 AFTER `last_id`',
  'DO 0'
);
PREPARE _mig FROM @ddl;
EXECUTE _mig;
DEALLOCATE PREPARE _mig;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_android`.`record_counts` TO 'aware_analytics'@'%';

USE `aware_ios`;

CREATE TABLE IF NOT EXISTS `record_counts` (
  `sensor`     varchar(64)     NOT NULL,
  `device_id`  varchar(150)    NOT NULL,
  `count`      bigint unsigned NOT NULL DEFAULT 0,
  `last_id`    bigint unsigned NOT NULL DEFAULT 0,
  `last_ts`    double          NOT NULL DEFAULT 0,
  `updated_at` timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`sensor`, `device_id`),
  KEY `sensor_idx` (`sensor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @ddl := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = 'aware_ios' AND TABLE_NAME = 'record_counts'
       AND COLUMN_NAME = 'last_ts') = 0,
  'ALTER TABLE `aware_ios`.`record_counts` ADD COLUMN `last_ts` double NOT NULL DEFAULT 0 AFTER `last_id`',
  'DO 0'
);
PREPARE _mig FROM @ddl;
EXECUTE _mig;
DEALLOCATE PREPARE _mig;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_ios`.`record_counts` TO 'aware_analytics'@'%';

FLUSH PRIVILEGES;
