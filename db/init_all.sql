-- GENERATED FILE - DO NOT EDIT.
-- Built by db/build_init_all.py from 00-bootstrap.sql, android-tables.sql
-- and ios-tables.sql. Edit those and re-run the script.

CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

-- The passwords below are only a first-boot seed: on a fresh data directory
-- zz-participant-password.sh replaces them with the per-deployment passwords
-- generated into .env. CREATE USER IF NOT EXISTS means replaying this file on later
-- restarts never resets those passwords.

-- The account an Android phone opens the database with itself, which is what the
-- direct dataflow asks of a phone. Inserts and nothing else: a phone delivers rows
-- and reads nothing back, and its credential travels in the study config every phone
-- downloads.
CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

-- The account the iOS micro-server writes with. iOS is webservice-only --- an iPhone
-- has no direct-database client --- so this is a server's credential, and the reads
-- its ingest makes are granted beside the tables they name.
CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

-- The Android micro-server's own account. On the webservice dataflow every write is
-- the server's and no phone opens MySQL at all, so ingest authenticates as the server
-- rather than as a participant.
--
-- Schema-wide INSERT is the data itself, and it is also what makes each table visible
-- in information_schema, which is where ingest reads the column list it writes a table
-- in the shape of: a table is listed there for an account holding any privilege on it.
-- The rows ingest reads back are granted table by table, beside the tables they name,
-- so this account sees the registry it checks and the metadata row it fills in rather
-- than the sensor data it writes.
CREATE USER IF NOT EXISTS 'aware_android_server'@'%' IDENTIFIED BY 'serverpass';
GRANT INSERT ON aware_android.* TO 'aware_android_server'@'%';

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
  `label` text,
  PRIMARY KEY (`_id`),
  KEY `time_device` (`timestamp`,`device_id`),
  -- One row per device, rewritten in place when the reported metadata changes,
  -- so this index serves that lookup rather than a per-change history.
  KEY `device_time` (`device_id`,`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Reconciles a deployed table with the shape declared above: CREATE TABLE applies
-- to a table that is absent, so a column the declaration gained lands through this
-- block instead. The client's device-profile insert names `label` and the
-- dashboard's device list reads the row whole, so both require it to be present.
SET @ddl := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'aware_device'
       AND COLUMN_NAME = 'label') = 0,
  'ALTER TABLE `aware_device` ADD COLUMN `label` text AFTER `sdk`',
  'DO 0'
);
PREPARE _mig FROM @ddl;
EXECUTE _mig;
DEALLOCATE PREPARE _mig;

-- The micro-server keeps one row per device current here: it reads the row it
-- already holds and fills in the hardware fields when the phone reports them, so
-- ingest needs to see and update this table as well as insert into it.
GRANT SELECT, UPDATE ON aware_android.aware_device TO 'aware_android_server'@'%';

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
--
-- `coverage_hourly` answers how much arrived per hour, which `record_counts`
-- cannot: it holds totals only. It is keyed by *table* rather than by sensor,
-- because each table carries its own `_id` sequence and so its own watermark —
-- which is what lets a sensor stored across two tables (`esm`, `wifi`) be
-- counted at all, and lets the builder walk every timestamped table instead of a
-- registry. `last_id` rides on the row, so a table's watermark is
-- `MAX(last_id)` for it and clearing the table clears its watermark.
--
-- `device_enrolment` holds when each phone was in the study, as one row per
-- window: a device that joined, quit and rejoined has two. The heatmap reads it
-- to tell "nothing expected" from "expected and missing", which a single window
-- per device would get wrong across exactly the gap a rejoin leaves behind.
--
-- Android only. An iPhone records its study state in NSUserDefaults and never
-- uploads it, so there is nothing on the server to derive a window from; iOS
-- devices are left without enrolment information rather than given an invented
-- join time.

-- `refusals` holds what the micro-server turned away, one row per
-- (device, reason) rather than one per attempt: a refused write stores nothing,
-- so without this the only trace is a line in a container log and the dashboard
-- has nothing to show. It carries the attempt and row counts, the table last
-- tried, and when the first and last attempt happened, which is what tells a
-- one-off test insert from a phone that has been retrying for a week.
--
-- Written by the participant account the micro-server connects as, which is why
-- that account is granted more than INSERT on this one table: the record is an
-- upsert whose `attempts = attempts + 1` reads the column it writes, so MySQL
-- requires SELECT on it as well as UPDATE.
--
-- `device_exclusions` names the devices a researcher has taken out of the
-- analysis. Withdrawal stops new data arriving; this answers the separate
-- question of what happens to the data already collected, which consent forms
-- answer differently. The rows stay in the database and stay on screen: an
-- exclusion the dashboard hid would be indistinguishable from a participant who
-- never took part. What it changes is the exports, which is where the analysis
-- dataset actually leaves.
--
-- `device_contacts` is deliberately not a sensor table. The micro-server
-- upserts one row after a batch is accepted, using its own clock, so the
-- dashboard can distinguish a reachable phone from one whose newest research
-- measurement is old. It has no `timestamp` column so coverage discovery does
-- not mistake it for participant data.

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

CREATE TABLE IF NOT EXISTS `coverage_hourly` (
  `table_name` varchar(64)     NOT NULL,
  `device_id`  varchar(150)    NOT NULL,
  `hour_start` bigint unsigned NOT NULL,
  `records`    bigint unsigned NOT NULL DEFAULT 0,
  `last_id`    bigint unsigned NOT NULL DEFAULT 0,
  `updated_at` timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`table_name`, `device_id`, `hour_start`),
  KEY `hour_idx` (`hour_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_android`.`coverage_hourly` TO 'aware_analytics'@'%';

CREATE TABLE IF NOT EXISTS `device_contacts` (
  `device_id`    varchar(150)    NOT NULL,
  `last_contact` bigint unsigned NOT NULL,
  `last_table`   varchar(64)     NOT NULL DEFAULT '',
  `updated_at`   timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`),
  KEY `last_contact_idx` (`last_contact`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE ON `aware_android`.`device_contacts` TO 'aware_android_server'@'%';
REVOKE IF EXISTS SELECT, INSERT, UPDATE ON `aware_android`.`device_contacts` FROM 'aware_android_participant'@'%';

-- `join_source` records how the window's start was established: `study_event`
-- from the phone's own `aware_studies` row, `first_data` inferred from when data
-- first arrived, `manual` entered by a researcher. It is what separates a device
-- that never enrolled from one that enrolled before anyone was recording it.
CREATE TABLE IF NOT EXISTS `device_enrolment` (
  `device_id`    varchar(150)    NOT NULL,
  `joined_at`    bigint unsigned NOT NULL,
  `left_at`      bigint unsigned NULL DEFAULT NULL,
  `join_source`  varchar(16)     NOT NULL DEFAULT 'first_data',
  `left_source`  varchar(16)     NULL DEFAULT NULL,
  `updated_at`   timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`, `joined_at`),
  KEY `joined_idx` (`joined_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_android`.`device_enrolment` TO 'aware_analytics'@'%';

-- `messages_sent` is what a researcher asked of a phone: a sync request, a question
-- or a notice. It is the third of the three states a prompt has, and the only one
-- this side owns --- what arrived is the phone's own `mqtt_messages` row, and what
-- came back is its `esms` row. Without it a dashboard could show what a participant
-- answered and never what they were asked.
--
-- Deliberately no `timestamp` column: the coverage rollup walks every timestamped
-- table it finds, and a table of researcher actions arriving on the coverage grid as
-- a sensor nobody configured would be wrong in a way that is hard to see. `sent_at`
-- carries the same value under a name the builder does not look for.
--
-- It also carries the rate limit. A limit needs to know what was already sent, and
-- this is the record of exactly that, so counting rows in a window is the whole of it.
CREATE TABLE IF NOT EXISTS `messages_sent` (
  `_id`       bigint unsigned NOT NULL AUTO_INCREMENT,
  `device_id` varchar(150)    NOT NULL,
  `channel`   varchar(32)     NOT NULL,
  `kind`      varchar(32)     NOT NULL,
  `title`     varchar(255)    NOT NULL DEFAULT '',
  `body`      text,
  `sent_at`   bigint unsigned NOT NULL,
  `sent_by`   varchar(64)     NOT NULL DEFAULT '',
  -- Whether the message's own words were kept. A researcher sending operational
  -- chatter -- charge your phone, we are away next week -- can ask for it not to
  -- enter the study record, and then `title` and `body` are empty here.
  --
  -- The row itself is written either way, and that is deliberate: the rate limit
  -- counts these, so a message that left no row would be a way past it, and a
  -- channel to participants that leaves no trace at all is not one a study should
  -- have. What is optional is the content, not the fact.
  `retained`  tinyint(1)      NOT NULL DEFAULT 1,
  PRIMARY KEY (`_id`),
  -- Both readers ask the same shape: everything sent to one device, newest first.
  -- The rate limit asks it over a window and the history asks it over a page.
  KEY `device_time` (`device_id`, `sent_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, DELETE ON `aware_android`.`messages_sent` TO 'aware_analytics'@'%';

SET @ddl := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = 'aware_android' AND TABLE_NAME = 'messages_sent'
       AND COLUMN_NAME = 'retained') = 0,
  'ALTER TABLE `messages_sent` ADD COLUMN `retained` tinyint(1) NOT NULL DEFAULT 1',
  'DO 0'
);
PREPARE _mig FROM @ddl;
EXECUTE _mig;
DEALLOCATE PREPARE _mig;

-- The micro-server reads this table to decide whether a device may write, so the
-- account it connects as needs to see it. Read-only: windows are derived by the
-- dashboard from the phone's own study log, never by the ingest path. Granted to the
-- server's account alone -- the gate runs in the server, and a phone writing straight
-- to the database reads nothing here.
GRANT SELECT ON `aware_android`.`device_enrolment` TO 'aware_android_server'@'%';
-- A deployment that once granted this to the participant account narrows it here.
-- The registry names every device in the study and when it joined, and the direct
-- path publishes the participant password to every phone.
REVOKE IF EXISTS SELECT ON `aware_android`.`device_enrolment` FROM 'aware_android_participant'@'%';

-- `reason` is why the write was turned away: `no_enrolment` for a device with no
-- window the study log put there, `no_device_id` for a request that named no
-- device at all. The latter aggregates under an empty `device_id`, since there is
-- no device to attribute it to.
CREATE TABLE IF NOT EXISTS `refusals` (
  `device_id`    varchar(150)    NOT NULL,
  `reason`       varchar(32)     NOT NULL,
  `attempts`     bigint unsigned NOT NULL DEFAULT 0,
  `rows_refused` bigint unsigned NOT NULL DEFAULT 0,
  `last_table`   varchar(64)     NOT NULL DEFAULT '',
  `first_seen`   bigint unsigned NOT NULL,
  `last_seen`    bigint unsigned NOT NULL,
  PRIMARY KEY (`device_id`, `reason`),
  KEY `last_seen_idx` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Counted up by the micro-server as it turns writes away, so the account the gate
-- runs as is the one that keeps this table.
GRANT SELECT, INSERT, UPDATE ON `aware_android`.`refusals` TO 'aware_android_server'@'%';
REVOKE IF EXISTS SELECT, INSERT, UPDATE ON `aware_android`.`refusals` FROM 'aware_android_participant'@'%';

-- One row per excluded device. `excluded_at` is when the researcher decided,
-- which is not necessarily when the participant left: a study can exclude
-- somebody who completed it. Undoing an exclusion deletes the row, since the
-- default state is to keep the data and there is nothing to record about a
-- device nobody excluded.
CREATE TABLE IF NOT EXISTS `device_exclusions` (
  `device_id`   varchar(150)    NOT NULL,
  `excluded_at` bigint unsigned NOT NULL,
  `note`        varchar(255)    NOT NULL DEFAULT '',
  `updated_at`  timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_android`.`device_exclusions` TO 'aware_analytics'@'%';

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

CREATE TABLE IF NOT EXISTS `coverage_hourly` (
  `table_name` varchar(64)     NOT NULL,
  `device_id`  varchar(150)    NOT NULL,
  `hour_start` bigint unsigned NOT NULL,
  `records`    bigint unsigned NOT NULL DEFAULT 0,
  `last_id`    bigint unsigned NOT NULL DEFAULT 0,
  `updated_at` timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`table_name`, `device_id`, `hour_start`),
  KEY `hour_idx` (`hour_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_ios`.`coverage_hourly` TO 'aware_analytics'@'%';

CREATE TABLE IF NOT EXISTS `device_contacts` (
  `device_id`    varchar(150)    NOT NULL,
  `last_contact` bigint unsigned NOT NULL,
  `last_table`   varchar(64)     NOT NULL DEFAULT '',
  `updated_at`   timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`),
  KEY `last_contact_idx` (`last_contact`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE ON `aware_ios`.`device_contacts` TO 'aware_ios_participant'@'%';

-- `reason` is why the write was turned away: `no_enrolment` for a device with no
-- window the study log put there, `no_device_id` for a request that named no
-- device at all. The latter aggregates under an empty `device_id`, since there is
-- no device to attribute it to.
CREATE TABLE IF NOT EXISTS `refusals` (
  `device_id`    varchar(150)    NOT NULL,
  `reason`       varchar(32)     NOT NULL,
  `attempts`     bigint unsigned NOT NULL DEFAULT 0,
  `rows_refused` bigint unsigned NOT NULL DEFAULT 0,
  `last_table`   varchar(64)     NOT NULL DEFAULT '',
  `first_seen`   bigint unsigned NOT NULL,
  `last_seen`    bigint unsigned NOT NULL,
  PRIMARY KEY (`device_id`, `reason`),
  KEY `last_seen_idx` (`last_seen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE ON `aware_ios`.`refusals` TO 'aware_ios_participant'@'%';

-- One row per excluded device. `excluded_at` is when the researcher decided,
-- which is not necessarily when the participant left: a study can exclude
-- somebody who completed it. Undoing an exclusion deletes the row, since the
-- default state is to keep the data and there is nothing to record about a
-- device nobody excluded.
CREATE TABLE IF NOT EXISTS `device_exclusions` (
  `device_id`   varchar(150)    NOT NULL,
  `excluded_at` bigint unsigned NOT NULL,
  `note`        varchar(255)    NOT NULL DEFAULT '',
  `updated_at`  timestamp       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT SELECT, INSERT, UPDATE, DELETE ON `aware_ios`.`device_exclusions` TO 'aware_analytics'@'%';

FLUSH PRIVILEGES;
