-- Run ONLY after the multi-trip app code is deployed everywhere (see
-- migrate_fuel_po_trips.sql). tripId was intentionally left NULL-able there so that,
-- during the window between running that migration and deploying the new code, the OLD
-- create_fuel_po (which inserts destinations without a tripId) would still succeed rather
-- than fail with "Field 'tripId' doesn't have a default value" mid-submission.
--
-- Verify first - this must return 0 before running:
--     SELECT COUNT(*) FROM db_os_2026.tbl_fuel_po_destinations WHERE tripId IS NULL;
SET @is_nullable = (
    SELECT IS_NULLABLE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_po_destinations'
      AND COLUMN_NAME = 'tripId'
);
SET @sql = IF(@is_nullable = 'YES',
    'ALTER TABLE db_os_2026.tbl_fuel_po_destinations MODIFY COLUMN tripId INT NOT NULL',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
