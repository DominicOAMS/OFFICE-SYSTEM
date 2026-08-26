-- Adds a pack-size (box) conversion to tbl_inventory_items: how many baseUnit make up one
-- purchaseUnit (e.g. baseUnit=PCS, purchaseUnit=BOX, packSize=10). NULL means "no box
-- concept for this item" - Stock In/Out then only accepts entries in the base unit.
-- Guarded/idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_inventory_items'
      AND COLUMN_NAME = 'packSize'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_inventory_items
        ADD COLUMN packSize INT NULL AFTER purchaseUnit',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
