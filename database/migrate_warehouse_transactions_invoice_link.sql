-- Migration: adds tbl_warehouse_transactions.invoiceId, linking a transaction back to the
-- Invoice that caused it - the new Invoices module auto-creates a Stock Out transaction when
-- an invoice is recorded, and this is that link.
--
-- The link lives here (on the transaction), not as a column on tbl_invoices, because it's
-- confirmed many-to-one: 236 legacy invoices have between 2 and 7 matching warehouse
-- transactions (via siNumber = InvoiceNum), so a single FK on the invoice side would be
-- structurally wrong. Same reasoning as the existing purchaseOrderId column on this same
-- table - placed right after it, since they're the same kind of link.
--
-- Backfilled from history: tbl_warehouse_transactions rows with reason IN ('Invoice',
-- 'Invoice Void') already carry an siNumber (Sales Invoice Number) from an earlier migration
-- this project. 5,004 of 5,057 such rows have an siNumber matching a real tbl_invoices row
-- (the rest reference an invoice number that no longer resolves to anything and stay NULL).
-- Scoped to those two `reason` values specifically so a Manual/DR transaction with a
-- coincidentally-matching siNumber can't get falsely linked.
--
-- This migration requires migrate_invoices.sql to have already run (tbl_invoices must exist).

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transactions'
      AND COLUMN_NAME = 'invoiceId'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transactions
        ADD COLUMN invoiceId INT NULL AFTER purchaseOrderId,
        ADD KEY idx_tbl_warehouse_transactions_invoiceId (invoiceId),
        ADD CONSTRAINT fk_tbl_warehouse_transactions_invoice
            FOREIGN KEY (invoiceId) REFERENCES db_os_2026.tbl_invoices (id)
            ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE db_os_2026.tbl_warehouse_transactions wt
JOIN db_os_2026.tbl_invoices i ON i.invoiceNumber = wt.siNumber
SET wt.invoiceId = i.id
WHERE wt.reason IN ('Invoice', 'Invoice Void')
  AND wt.invoiceId IS NULL;
