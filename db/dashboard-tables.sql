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

-- The micro-server reads this table to decide whether a device may write, so the
-- account it connects as needs to see it. Read-only: windows are derived by the
-- dashboard from the phone's own study log, never by the ingest path.
GRANT SELECT ON `aware_android`.`device_enrolment` TO 'aware_android_participant'@'%';

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

GRANT SELECT, INSERT, UPDATE ON `aware_android`.`refusals` TO 'aware_android_participant'@'%';

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
