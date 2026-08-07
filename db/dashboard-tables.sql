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
