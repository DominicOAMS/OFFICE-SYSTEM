-- Fuel estimation was originally built to route from one fixed company origin. Changed
-- to let the requester pick their own starting point per request (their current
-- location), not just the destination - tbl_company_settings' origin now only serves as
-- a default pre-fill for convenience, not the value actually used in the calculation.
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_pos' AND COLUMN_NAME = 'startLocation'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_pos
        ADD COLUMN startLocation VARCHAR(255) NULL AFTER requestedByUserId,
        ADD COLUMN startLat DECIMAL(10,7) NULL AFTER startLocation,
        ADD COLUMN startLng DECIMAL(10,7) NULL AFTER startLat',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
