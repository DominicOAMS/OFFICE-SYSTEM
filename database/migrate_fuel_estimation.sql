-- Fuel estimation: adds what the Add Fuel PO map-based estimate needs on top of the
-- existing tbl_vehicles/tbl_fuel_pos from migrate_fuel_po.sql, plus two new small config
-- tables. Idempotent (safe to re-run): ALTERs are guarded, seed rows use INSERT IGNORE.

-- tbl_vehicles: each vehicle needs a fuel efficiency (km/L) and which of the 3 DOE pricing
-- categories its fuel maps to (fuelType stays free text for display/history - brand blend
-- names like "V-POWER RACING" don't match DOE's broad reporting categories directly).
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_vehicles' AND COLUMN_NAME = 'fuelEfficiencyKmPerLiter'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_vehicles
        ADD COLUMN fuelEfficiencyKmPerLiter DECIMAL(5,2) NULL AFTER fuelType,
        ADD COLUMN fuelPriceCategory VARCHAR(20) NULL AFTER fuelEfficiencyKmPerLiter',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- tbl_fuel_pos: preserve what was actually estimated at submission time (audit trail),
-- separate from amountRequested which is what the requester actually submits/edits.
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_pos' AND COLUMN_NAME = 'destinationLat'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_pos
        ADD COLUMN destinationLat DECIMAL(10,7) NULL AFTER destination,
        ADD COLUMN destinationLng DECIMAL(10,7) NULL AFTER destinationLat,
        ADD COLUMN estimatedDistanceKm DECIMAL(7,2) NULL AFTER destinationLng,
        ADD COLUMN estimatedAmount DECIMAL(12,2) NULL AFTER estimatedDistanceKm',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Current peso/liter per DOE pricing category. pricePerLiter starts NULL - "not set up
-- yet" - filled in by an admin on the new Parameters > Fuel Prices page.
CREATE TABLE IF NOT EXISTS db_os_2026.tbl_fuel_prices (
    id INT NOT NULL AUTO_INCREMENT,
    fuelCategory VARCHAR(20) NOT NULL,
    pricePerLiter DECIMAL(6,2) NULL,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_fuel_prices_fuelCategory (fuelCategory),
    CONSTRAINT fk_tbl_fuel_prices_updatedBy
        FOREIGN KEY (updatedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO db_os_2026.tbl_fuel_prices (fuelCategory, pricePerLiter)
VALUES ('Diesel', NULL), ('Unleaded', NULL), ('Premium', NULL);

-- Single-row settings table holding the trip origin that distances are routed from.
CREATE TABLE IF NOT EXISTS db_os_2026.tbl_company_settings (
    id INT NOT NULL AUTO_INCREMENT,
    originAddress VARCHAR(500) NULL,
    originLat DECIMAL(10,7) NULL,
    originLng DECIMAL(10,7) NULL,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_tbl_company_settings_updatedBy
        FOREIGN KEY (updatedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO db_os_2026.tbl_company_settings (id) VALUES (1);
