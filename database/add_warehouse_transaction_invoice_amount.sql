-- Adds an optional invoice-amount reference field for Stock-In(Purchase Order), matching
-- legacy's "SI Price" field on its PO stock-in header (tbl_transaction.InvoicePrice) - kept
-- as a plain reference number here too (not wired into Payables/accounting, same as legacy
-- where it was effectively vestigial: disabled input defaulting to 0, never read back out
-- by any downstream logic). Guarded/idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transactions'
      AND COLUMN_NAME = 'invoiceAmount'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transactions
        ADD COLUMN invoiceAmount DECIMAL(12,2) NULL AFTER supplierInvoice',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
