-- Migration: db_oams_app_2026.tbl_delivery_receipt / tbl_dr_details
--         -> db_os_2026.tbl_delivery_receipts / tbl_delivery_receipt_items
--
-- The formal customer-facing proof-of-delivery document. Cross-references (not wraps)
-- tbl_warehouse_transactions, which already has its own free-text drNumber column - goods
-- movement is still that table's job; this is the document layer on top of it.
--
-- Notes on the source data (profiled before writing this):
--   * id is a fresh surrogate; legacy DRNum is kept as a separate UNIQUE drNumber business
--     column instead of being reused as the PK. DR numbers are a clean, tightly-sequential
--     integer series (a software sequence, like invoiceNumber/poNumber), not a physical
--     pre-printed booklet number like Payables' OR numbers - same reasoning that put
--     invoiceNumber/poNumber in their own column rather than reusing them as the PK the way
--     Warehouse Transactions reused transID.
--   * CustomerID resolves to tbl_customers.code for 328 of 328 rows (100%). customerCode/
--     deliveredTo/tin/address are snapshotted from the legacy row's OWN text regardless of
--     match - this document already recorded that text itself, so "freeze what it said"
--     means keeping what THIS document said, not a live join to the customer's current
--     record.
--   * DeliveryDate is VARCHAR on the legacy table (not a real DATE column) - same
--     REGEXP-then-NULL guard as every other migration's dirty date columns.
--   * PONum (customerPo here) is kept as free text - format is inconsistent
--     (e.g. "2026-04-15137"), not worth forcing into a Purchase Order lookup.
--   * Status is already exactly Created/Printed/Finished/Voided in the source (12/306/7/3
--     rows) - copied verbatim, only "Voided" -> "Void" to match this project's status-name
--     convention everywhere else (Payables/Vouchers/Collections all use "Void").
--   * transactionId is resolved in a separate follow-up UPDATE (not this INSERT) by matching
--     drNumber against tbl_warehouse_transactions' own free-text drNumber column - confirmed
--     316 of 330 legacy DR numbers resolve this way (the other 14 either predate that
--     table's own data or were never cross-referenced there).
--   * No column on the legacy table ever recorded *who* created a delivery receipt -
--     createdBy is NULL for every migrated row, the same gap already documented for every
--     other module without a creator column.
--   * created_at/updated_at are VARCHAR on the legacy table, hence CAST(... AS DATETIME).
--   * tbl_delivery_receipt / tbl_dr_details are already utf8mb4 - COLLATE utf8mb4_unicode_ci
--     is enough for the cross-database join, no CONVERT needed.
--
--   Line items (tbl_dr_details, 1,342 rows):
--   * Catalog resolves to tbl_inventory_items.catalog - migrated regardless of match, same
--     "freeze what it said" reasoning as every other line-item migration.
--   * Expiry is already a real DATE column on this table (unlike DeliveryDate above) - no
--     REGEXP guard needed, just a straight copy.
--   * PONumber is kept as its own per-line snapshot in case it ever differs from the
--     header's PONum - same defensive "don't silently drop a per-line variance" instinct.
--   * sequence does not exist in the source; reconstructed here from each line's original
--     insertion order within its DRNum, using the same MySQL 5.7 session-variable running
--     count every prior line-item migration on this server has used (no window functions).
--   * 6 line items reference a DRNum with no matching header row and are not migrated -
--     6 of 1,342 (0.4%), the same class of orphan every other migration has dropped.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_delivery_receipts (
    id INT NOT NULL AUTO_INCREMENT,
    drNumber VARCHAR(20) NOT NULL,
    customerId INT NOT NULL,
    customerCode VARCHAR(50) NULL,
    deliveredTo VARCHAR(255) NULL,
    tin VARCHAR(255) NULL,
    address VARCHAR(255) NULL,
    deliveryDate DATE NULL,
    customerPo VARCHAR(255) NULL,
    terms VARCHAR(255) NULL,
    branch VARCHAR(100) NULL,
    transactionId INT NULL,
    notes TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Created',
    voidedBy INT NULL,
    voidedAt DATETIME NULL,
    voidReason VARCHAR(255) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_delivery_receipts_drNumber (drNumber),
    KEY idx_tbl_delivery_receipts_customerId (customerId),
    KEY idx_tbl_delivery_receipts_status (status),
    KEY idx_tbl_delivery_receipts_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_delivery_receipts_customer
        FOREIGN KEY (customerId) REFERENCES db_os_2026.tbl_customers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_delivery_receipts_transaction
        FOREIGN KEY (transactionId) REFERENCES db_os_2026.tbl_warehouse_transactions (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_delivery_receipts_voidedBy
        FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_delivery_receipt_items (
    id INT NOT NULL AUTO_INCREMENT,
    deliveryReceiptId INT NOT NULL,
    sequence INT NOT NULL,
    itemId INT NULL,
    catalogCode VARCHAR(50) NULL,
    description VARCHAR(255) NULL,
    unit VARCHAR(30) NULL,
    category VARCHAR(50) NULL,
    quantity DECIMAL(12,2) NULL,
    lot VARCHAR(50) NULL,
    expiryDate DATE NULL,
    customerPo VARCHAR(255) NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_delivery_receipt_items_dr_sequence (deliveryReceiptId, sequence),
    KEY idx_tbl_delivery_receipt_items_itemId (itemId),
    CONSTRAINT fk_tbl_delivery_receipt_items_dr
        FOREIGN KEY (deliveryReceiptId) REFERENCES db_os_2026.tbl_delivery_receipts (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_delivery_receipt_items_item
        FOREIGN KEY (itemId) REFERENCES db_os_2026.tbl_inventory_items (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_delivery_receipts
    (drNumber, customerId, customerCode, deliveredTo, tin, address, deliveryDate,
     customerPo, terms, branch, notes, status, isDeleted, createdBy, createdAt,
     updatedBy, updatedAt)
SELECT
    TRIM(dr.DRNum),
    cust.id,
    NULLIF(TRIM(dr.CustomerID), ''),
    NULLIF(TRIM(dr.DeliveredTo), ''),
    NULLIF(TRIM(dr.TIN), ''),
    NULLIF(TRIM(dr.Address), ''),
    CASE WHEN dr.DeliveryDate REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN dr.DeliveryDate ELSE NULL END,
    NULLIF(TRIM(dr.PONum), ''),
    NULLIF(TRIM(dr.Terms), ''),
    NULLIF(TRIM(dr.Branch), ''),
    NULLIF(TRIM(dr.Notes), ''),
    IF(TRIM(dr.Status) = 'Voided', 'Void', TRIM(dr.Status)),
    0, NULL, CAST(dr.created_at AS DATETIME), NULL, CAST(dr.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_delivery_receipt dr
JOIN db_os_2026.tbl_customers cust
    ON cust.code = TRIM(dr.CustomerID) COLLATE utf8mb4_unicode_ci;

SET @dr := '', @seq := 0;

INSERT INTO db_os_2026.tbl_delivery_receipt_items
    (deliveryReceiptId, sequence, itemId, catalogCode, description, unit, category,
     quantity, lot, expiryDate, customerPo, createdAt, updatedAt)
SELECT
    r.id,
    ordered.sequence,
    inv.id,
    NULLIF(TRIM(ordered.Catalog), ''),
    NULLIF(TRIM(ordered.Description), ''),
    NULLIF(TRIM(ordered.Unit), ''),
    NULLIF(TRIM(ordered.Category), ''),
    ordered.Quantity,
    NULLIF(TRIM(ordered.LotNumber), ''),
    ordered.Expiry,
    NULLIF(TRIM(ordered.PONumber), ''),
    CAST(ordered.created_at AS DATETIME),
    CAST(ordered.updated_at AS DATETIME)
FROM (
    SELECT
        d.*,
        @seq := IF(@dr = d.DRNum, @seq + 1, 1) AS sequence,
        @dr := d.DRNum AS _dr_marker
    FROM db_oams_app_2026.tbl_dr_details d
    ORDER BY d.DRNum, d.itemNo
    LIMIT 18446744073709551615
) ordered
JOIN db_os_2026.tbl_delivery_receipts r
    ON r.drNumber = TRIM(ordered.DRNum) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_inventory_items inv
    ON inv.catalog = TRIM(ordered.Catalog) COLLATE utf8mb4_unicode_ci
   AND inv.isDeleted = 0;

UPDATE db_os_2026.tbl_delivery_receipts r
JOIN db_os_2026.tbl_warehouse_transactions wt
    ON wt.drNumber = r.drNumber COLLATE utf8mb4_unicode_ci
SET r.transactionId = wt.id
WHERE r.transactionId IS NULL;
