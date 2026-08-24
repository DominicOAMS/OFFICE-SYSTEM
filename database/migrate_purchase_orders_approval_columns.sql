-- Adds the approval-workflow columns to tbl_purchase_orders that the legacy
-- data never had (same gap documented for Fuel PO's tbl_fuel_pos). Guarded/
-- idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_purchase_orders'
      AND COLUMN_NAME = 'approverUserId'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_purchase_orders
        ADD COLUMN approverUserId INT NULL AFTER branch,
        ADD COLUMN approverActionAt DATETIME NULL AFTER approverUserId,
        ADD COLUMN approverRemarks VARCHAR(255) NULL AFTER approverActionAt,
        ADD KEY idx_tbl_purchase_orders_approverUserId (approverUserId),
        ADD CONSTRAINT fk_tbl_purchase_orders_approver
            FOREIGN KEY (approverUserId) REFERENCES db_os_2026.tbl_users (id)
            ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
