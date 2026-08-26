-- Adds Void tracking to tbl_warehouse_transactions, replacing hard/soft delete for this
-- module: a transaction is never removed from the records, only marked 'Void' (a new
-- status value alongside Created/Verified/Finished - VARCHAR(20) already fits it, no
-- column resize needed). Guarded/idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transactions'
      AND COLUMN_NAME = 'voidedBy'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transactions
        ADD COLUMN voidedBy INT NULL AFTER finishedAt,
        ADD COLUMN voidedAt DATETIME NULL AFTER voidedBy,
        ADD COLUMN voidReason VARCHAR(255) NULL AFTER voidedAt,
        ADD KEY idx_tbl_warehouse_transactions_voidedBy (voidedBy),
        ADD CONSTRAINT fk_tbl_warehouse_transactions_voider
            FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
            ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
