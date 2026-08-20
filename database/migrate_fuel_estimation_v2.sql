-- Two changes to the fuel estimate flow:
--   1. Fuel efficiency (km/L) is now entered by the requester per-request (pre-filled from
--      the vehicle's default if set, but always editable) rather than being a hard
--      requirement configured once on the vehicle - tbl_fuel_pos now records what was
--      actually used for that request's estimate.
--   2. A Fuel PO can now have multiple destinations (a multi-stop trip), so destinations
--      move into their own child table instead of the single destination/destinationLat/
--      destinationLng columns. Those columns stay on tbl_fuel_pos for backward
--      compatibility with existing display code (destination becomes a joined summary of
--      all stops; destinationLat/destinationLng are no longer populated for new rows since
--      the child table is now the source of truth for coordinates).

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_pos' AND COLUMN_NAME = 'fuelEfficiencyKmPerLiter'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_pos ADD COLUMN fuelEfficiencyKmPerLiter DECIMAL(5,2) NULL AFTER fuelType',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_fuel_po_destinations (
    id INT NOT NULL AUTO_INCREMENT,
    fuelPoId INT NOT NULL,
    sequence INT NOT NULL,
    destination VARCHAR(255) NOT NULL,
    destinationLat DECIMAL(10,7) NOT NULL,
    destinationLng DECIMAL(10,7) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tbl_fuel_po_destinations_fuelPoId (fuelPoId),
    CONSTRAINT fk_tbl_fuel_po_destinations_fuelPo
        FOREIGN KEY (fuelPoId) REFERENCES db_os_2026.tbl_fuel_pos (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
