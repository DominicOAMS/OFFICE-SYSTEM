-- Migration: db_oams_app_2026.tbl_transaction / tbl_transactionprod
--         -> db_os_2026.tbl_warehouse_transactions / tbl_warehouse_transaction_items
--
-- Follows the same shape as migrate_fuel_po.sql / migrate_purchase_orders.sql: renames
-- columns to lowerCamelCase, re-types them, adds audit-trail columns, and replaces
-- legacy free-text/embedded-string signals with real categories and a real foreign key.
--
-- Notes on the source data (profiled before writing this):
--   * transID is preserved as `id` (explicit INSERT, like Fuel PO's FPONumber) rather than
--     given a fresh surrogate key: it's a clean, staff-recognized sequence (1..8252, 8,215
--     rows - 37 gaps from historical deletions, not corruption) that already functions as
--     this transaction's number. AUTO_INCREMENT is reset to 8253 afterward.
--   * transType is a legacy free-text field that embeds TWO different signals in one
--     string: a direction ("Stock In" / "Stock Out") and, for Stock Out, sometimes a DR
--     number baked directly into the string ("Stock Out(DR #6206)" - 317 rows, one distinct
--     value PER transaction, so grouping by the raw string is meaningless). Split into a
--     clean `direction` ('IN'/'OUT', covers all 8,215 rows with zero unrecognized values)
--     and a `reason` category (Purchase Order / Invoice / Invoice Void / Customer Return /
--     DR / Manual). The embedded DR number is extracted into `drNumber` when that column
--     itself is blank (it always was, for these 317 rows - the legacy app apparently only
--     ever recorded the DR number in the type string for stock-outs, never in its own
--     column). The raw original string is kept verbatim in `legacyTransType`.
--   * PONumber on `reason = 'Purchase Order'` rows resolves to the just-migrated
--     `tbl_purchase_orders.poNumber` for every single non-blank case (2,176 of 2,195 rows;
--     the other 19 simply have no PONumber recorded at all) - a real, useful cross-module
--     link, added as `purchaseOrderId`. `poNumber` itself is kept too, as free text, since
--     the FK can't carry the 19 blank-but-still-meaningful-as-history rows.
--   * careTO means different things depending on direction - the receiving staff member's
--     name for Stock In, the customer/clinic name for Stock Out - so it can never be a
--     single clean FK either way and is kept as plain text (`careTo`), not resolved.
--   * `noOfItems` and `InvoicePrice` are NULL on all 8,215 rows and are not migrated - same
--     call migrate_suppliers.sql made for always-blank legacy columns.
--   * `Status` ('Created'/'Verified'/'Finished') is already a clean, meaningful workflow
--     state and is kept as-is, unlike Fuel PO's status collapsing - nothing here needs
--     reinterpreting.
--   * created_at/updated_at are VARCHAR but already well-formed 'YYYY-MM-DD HH:MM:SS' on
--     every row of both tables (0 rows fail the format check), so a plain CAST to DATETIME
--     is enough.
--
--   Line items (tbl_transactionprod, 31,726 rows):
--   * prodId resolves to tbl_inventory_items.catalog for 26,169 of 31,726 rows (927
--     distinct codes used; the "Other Products" category's codes look like supplier-style
--     catalog numbers, e.g. "JP2023002", likely tracked in tbl_suppliers_products instead -
--     not resolved here). catalogCode/description/unit/category are copied onto every line
--     regardless of match, for the same "freeze what it said" reasoning used for Purchase
--     Orders' line items.
--   * 11 line items reference a TransID with no matching header row and are not migrated -
--     0.03% of rows, same as the 5 orphan Purchase Order line items found earlier.
--   * prodDesc is TEXT and runs up to 904 characters (well past VARCHAR(255) - this is
--     exactly the overflow class of bug the Purchase Order migration's `allocation` field
--     hit), so `description` is TEXT here from the start.
--   * quantity/lot/Expiry are already clean (quantity is INT with 4 NULLs kept as NULL;
--     Expiry is a well-formed date string on every populated row; 9 rows are genuinely
--     quantity=0, not blank/junk, and are kept as real zero-quantity lines).
--   * 34 line items (all under one transaction, #5363) have NULL created_at/updated_at -
--     these fall back to their parent transaction's own timestamp rather than NOW(), since
--     the transaction they belong to does have a real recorded time.
--   * `sequence` (order within its transaction) does not exist in the source; reconstructed
--     from each line's original auto-increment order within its TransID, using the same
--     MySQL 5.7 session-variable running-count trick migrate_purchase_orders.sql used (this
--     server has no window functions - MySQL 5.7).
--   * tbl_transaction / tbl_transactionprod are utf8mb4_general_ci while the new tables are
--     utf8mb4_unicode_ci, so every cross-database string comparison below explicitly
--     collates to avoid "illegal mix of collations" (no CONVERT needed, both sides are
--     already utf8mb4).

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_warehouse_transactions (
    id INT NOT NULL AUTO_INCREMENT,
    direction VARCHAR(3) NOT NULL,
    reason VARCHAR(30) NOT NULL,
    legacyTransType VARCHAR(50) NULL,
    careTo VARCHAR(255) NULL,
    note VARCHAR(255) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Created',
    purchaseOrderId INT NULL,
    poNumber VARCHAR(20) NULL,
    siNumber VARCHAR(50) NULL,
    customerPo VARCHAR(100) NULL,
    supplierInvoice VARCHAR(100) NULL,
    drNumber VARCHAR(50) NULL,
    supplierDrNumber VARCHAR(50) NULL,
    branch VARCHAR(100) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_warehouse_transactions_purchaseOrderId (purchaseOrderId),
    KEY idx_tbl_warehouse_transactions_direction (direction),
    KEY idx_tbl_warehouse_transactions_status (status),
    KEY idx_tbl_warehouse_transactions_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_warehouse_transactions_po
        FOREIGN KEY (purchaseOrderId) REFERENCES db_os_2026.tbl_purchase_orders (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_warehouse_transaction_items (
    id INT NOT NULL AUTO_INCREMENT,
    transactionId INT NOT NULL,
    sequence INT NOT NULL,
    itemId INT NULL,
    catalogCode VARCHAR(50) NULL,
    description TEXT NULL,
    unit VARCHAR(30) NULL,
    category VARCHAR(50) NULL,
    quantity INT NULL,
    lot VARCHAR(50) NULL,
    expiryDate DATE NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_warehouse_transaction_items_txn_sequence (transactionId, sequence),
    KEY idx_tbl_warehouse_transaction_items_itemId (itemId),
    CONSTRAINT fk_tbl_warehouse_transaction_items_txn
        FOREIGN KEY (transactionId) REFERENCES db_os_2026.tbl_warehouse_transactions (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_warehouse_transaction_items_item
        FOREIGN KEY (itemId) REFERENCES db_os_2026.tbl_inventory_items (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) Transaction headers. id is explicitly set to the legacy transID (see header note).
INSERT INTO db_os_2026.tbl_warehouse_transactions
    (id, direction, reason, legacyTransType, careTo, note, status,
     purchaseOrderId, poNumber, siNumber, customerPo, supplierInvoice,
     drNumber, supplierDrNumber, branch, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    t.transID,
    CASE WHEN t.transType LIKE 'Stock In%' THEN 'IN' ELSE 'OUT' END,
    CASE
        WHEN t.transType IN ('Stock In', 'Stock Out') THEN 'Manual'
        WHEN t.transType LIKE '%(Purchase Order)' THEN 'Purchase Order'
        WHEN t.transType LIKE '%(Invoice Void)' THEN 'Invoice Void'
        WHEN t.transType LIKE '%(Customer Return)' THEN 'Customer Return'
        WHEN t.transType LIKE '%(Invoice)' THEN 'Invoice'
        WHEN t.transType LIKE '%(DR #%' THEN 'DR'
        ELSE 'Manual'
    END,
    NULLIF(TRIM(t.transType), ''),
    NULLIF(TRIM(t.careTO), ''),
    NULLIF(TRIM(t.Note), ''),
    COALESCE(NULLIF(TRIM(t.Status), ''), 'Created'),
    po.id,
    NULLIF(TRIM(t.PONumber), ''),
    NULLIF(TRIM(t.SINumber), ''),
    NULLIF(TRIM(t.CustomerPO), ''),
    NULLIF(TRIM(t.SupplierInvoice), ''),
    COALESCE(
        NULLIF(TRIM(t.DRNumber), ''),
        CASE WHEN t.transType LIKE '%(DR #%'
             THEN SUBSTRING(
                 t.transType,
                 LOCATE('#', t.transType) + 1,
                 LENGTH(t.transType) - LOCATE('#', t.transType) - 1
             )
             ELSE NULL END
    ),
    NULLIF(TRIM(t.SupplierDRNumber), ''),
    NULLIF(TRIM(t.Branch), ''),
    0, NULL, CAST(t.created_at AS DATETIME), NULL, CAST(t.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_transaction t
LEFT JOIN db_os_2026.tbl_purchase_orders po
    ON po.poNumber = CONVERT(TRIM(t.PONumber) USING utf8mb4) COLLATE utf8mb4_unicode_ci
   AND t.transType = 'Stock In(Purchase Order)';

ALTER TABLE db_os_2026.tbl_warehouse_transactions AUTO_INCREMENT = 8253;

-- 2) Line items, linked through the new integer transactionId/itemId. sequence is
--    reconstructed from each line's original insertion order within its transaction (see
--    header note on the MySQL 5.7 session-variable technique).
SET @txn := '', @seq := 0;

INSERT INTO db_os_2026.tbl_warehouse_transaction_items
    (transactionId, sequence, itemId, catalogCode, description, unit, category,
     quantity, lot, expiryDate, createdAt, updatedAt)
SELECT
    ordered.TransID,
    ordered.sequence,
    inv.id,
    NULLIF(TRIM(ordered.prodId), ''),
    NULLIF(TRIM(ordered.prodDesc), ''),
    NULLIF(TRIM(ordered.Unit), ''),
    NULLIF(TRIM(ordered.Category), ''),
    ordered.quantity,
    NULLIF(TRIM(ordered.lot), ''),
    CASE WHEN ordered.Expiry REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN ordered.Expiry ELSE NULL END,
    CAST(COALESCE(ordered.created_at, parent.created_at) AS DATETIME),
    CAST(COALESCE(ordered.updated_at, parent.updated_at) AS DATETIME)
FROM (
    SELECT
        CAST(i.TransID AS UNSIGNED) AS TransID,
        i.prodId, i.prodDesc, i.Unit, i.Category, i.quantity, i.lot, i.Expiry,
        i.created_at, i.updated_at,
        @seq := IF(@txn = i.TransID, @seq + 1, 1) AS sequence,
        @txn := i.TransID AS _txn_marker
    FROM db_oams_app_2026.tbl_transactionprod i
    WHERE i.TransID REGEXP '^[0-9]+$'
    ORDER BY i.TransID, i.transProdNum
    LIMIT 18446744073709551615
) ordered
JOIN db_os_2026.tbl_warehouse_transactions wt ON wt.id = ordered.TransID
JOIN db_oams_app_2026.tbl_transaction parent ON parent.transID = ordered.TransID
LEFT JOIN db_os_2026.tbl_inventory_items inv
    ON inv.catalog = CONVERT(TRIM(ordered.prodId) USING utf8mb4) COLLATE utf8mb4_unicode_ci
   AND inv.isDeleted = 0;
