-- Links a Stock-In transaction line to the specific PO line it's receiving
-- against, so the receipt can increment that PO line's quantityServed instead
-- of just recording which PO the shipment relates to at the header level (the
-- purchaseOrderId column already on tbl_warehouse_transactions). Nullable -
-- Manual stock-ins and Stock-Out have no PO line to point at.
-- Guarded/idempotent so it is safe to run more than once.

SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_warehouse_transaction_items'
      AND COLUMN_NAME = 'purchaseOrderItemId'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_warehouse_transaction_items
        ADD COLUMN purchaseOrderItemId INT NULL AFTER itemId,
        ADD KEY idx_tbl_warehouse_transaction_items_poItemId (purchaseOrderItemId),
        ADD CONSTRAINT fk_tbl_warehouse_transaction_items_poItem
            FOREIGN KEY (purchaseOrderItemId) REFERENCES db_os_2026.tbl_purchase_order_items (id)
            ON DELETE RESTRICT ON UPDATE CASCADE',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
