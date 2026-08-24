-- Adds the verify/finish workflow columns to tbl_warehouse_transactions that the legacy
-- data never had (same gap documented for Fuel PO's approverUserId and Purchase Orders'
-- approverUserId). Guarded/idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transactions'
      AND COLUMN_NAME = 'verifiedBy'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transactions
        ADD COLUMN verifiedBy INT NULL AFTER status,
        ADD COLUMN verifiedAt DATETIME NULL AFTER verifiedBy,
        ADD COLUMN finishedBy INT NULL AFTER verifiedAt,
        ADD COLUMN finishedAt DATETIME NULL AFTER finishedBy,
        ADD KEY idx_tbl_warehouse_transactions_verifiedBy (verifiedBy),
        ADD KEY idx_tbl_warehouse_transactions_finishedBy (finishedBy),
        ADD CONSTRAINT fk_tbl_warehouse_transactions_verifier
            FOREIGN KEY (verifiedBy) REFERENCES db_os_2026.tbl_users (id)
            ON DELETE RESTRICT ON UPDATE CASCADE,
        ADD CONSTRAINT fk_tbl_warehouse_transactions_finisher
            FOREIGN KEY (finishedBy) REFERENCES db_os_2026.tbl_users (id)
            ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
