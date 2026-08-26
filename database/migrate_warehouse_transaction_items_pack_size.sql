-- Adds box/pack-size entry tracking to tbl_warehouse_transaction_items. `quantity` itself
-- is untouched and stays the canonical base-unit-equivalent total that list_stock_balances()
-- already sums - these two columns only record WHAT WAS TYPED, for display/audit:
--   enteredQuantity - the raw number entered (e.g. 5, for "5 BOX")
--   enteredPackSize - the item's packSize AT THE TIME, snapshotted so a later edit to the
--                     item's packSize can't silently reinterpret old history
-- Every existing row was, factually, entered directly in base units (no box concept
-- existed yet), so enteredQuantity backfills to the existing quantity and enteredPackSize
-- stays NULL - exactly what a fresh base-unit entry looks like today. Guarded/idempotent
-- so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transaction_items'
      AND COLUMN_NAME = 'enteredQuantity'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transaction_items
        ADD COLUMN enteredQuantity INT NULL AFTER quantity,
        ADD COLUMN enteredPackSize INT NULL AFTER enteredQuantity',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE db_os_2026.tbl_warehouse_transaction_items
SET enteredQuantity = quantity
WHERE enteredQuantity IS NULL;
