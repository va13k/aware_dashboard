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

FLUSH PRIVILEGES;
