-- Reclaims the space the physical sensors' `label` column occupies.
--
-- The ten tables below are the high-volume physical sensors, and the column holds
-- one empty string per row: the client fills it from an Android broadcast that a
-- study never sends. `bluetooth`, `locations` and `wifi` keep theirs, which the
-- client still declares and writes.
--
-- Run by hand, once per deployment, against the Android schema:
--
--     docker exec -i aware_mysql mysql -uroot -p<root-password> aware_android \
--       < db/reclaim-sensor-label.sql
--
-- Each table is dropped in its own statement, so a run that is interrupted leaves
-- every table either whole or reduced, and re-running finishes the rest. MySQL
-- 8.0.29 and later apply DROP COLUMN instantly; earlier 8.0 releases rebuild the
-- table, which on a sensor holding millions of rows is worth scheduling.

DROP PROCEDURE IF EXISTS _reclaim_sensor_label;

DELIMITER //
CREATE PROCEDURE _reclaim_sensor_label()
BEGIN
  DECLARE remaining TEXT DEFAULT 'accelerometer,barometer,gravity,gyroscope,light,linear_accelerometer,magnetometer,proximity,rotation,temperature';
  DECLARE sensor VARCHAR(64);

  WHILE CHAR_LENGTH(remaining) > 0 DO
    SET sensor = SUBSTRING_INDEX(remaining, ',', 1);
    SET remaining = IF(
      LOCATE(',', remaining) > 0,
      SUBSTRING(remaining, LOCATE(',', remaining) + 1),
      ''
    );

    IF (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = sensor
            AND COLUMN_NAME = 'label') > 0 THEN
      SET @ddl := CONCAT('ALTER TABLE `', sensor, '` DROP COLUMN `label`');
      PREPARE _drop FROM @ddl;
      EXECUTE _drop;
      DEALLOCATE PREPARE _drop;
      SELECT CONCAT(sensor, ': label dropped') AS result;
    ELSE
      SELECT CONCAT(sensor, ': matches the schema') AS result;
    END IF;
  END WHILE;
END //
DELIMITER ;

CALL _reclaim_sensor_label();

DROP PROCEDURE _reclaim_sensor_label;
