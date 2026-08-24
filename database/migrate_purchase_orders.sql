-- Migration: db_oams_app_2026.tbl_new_purchase / tbl_new_poproducts
--         -> db_os_2026.tbl_purchase_orders / tbl_purchase_order_items
--
-- Follows the same shape as migrate_suppliers.sql / migrate_fuel_po.sql:
-- renames columns to lowerCamelCase, re-types them, adds the audit-trail
-- columns, and replaces legacy free-text supplier/catalog links with real
-- foreign keys where they resolve.
--
-- Notes on the source data (profiled before writing this):
--   * tbl_new_purchase's PONumber ('2026-0380') is NOT usable as an integer
--     primary key like Fuel PO's FPONumber was, so this gets a fresh surrogate
--     `id`; poNumber is kept as a unique business-key column instead. There are
--     no duplicate or blank PONumbers in the source (1,773 rows, 1,773 unique).
--     How NEW purchase orders get numbered going forward is a product
--     decision for the workflow build, not this migration.
--   * SupplierID resolves to tbl_suppliers.code for 1,772 of 1,773 rows. The
--     one exception (R095, "PHILRX PHARMA INC.") lands with supplierId NULL.
--     Supplier name/address/telephone/fax/email are copied onto every PO
--     regardless of whether supplierId resolved - a PO should freeze what it
--     said about the supplier at the time it was issued, the same way an
--     invoice doesn't retroactively change if the vendor's address changes
--     later. This also means the one unmatched row needs no special-casing.
--   * Vatable/VAT/TotalSales are VARCHAR and hold a clean relationship
--     (Vatable * 1.12 = TotalSales = VAT + Vatable, i.e. standard 12% PH VAT,
--     and TotalSales matches SUM(line item Amount) on every spot-checked PO).
--     Cast straight to DECIMAL(14,2); only 1 row has incidental leading
--     whitespace (' 62100'), TRIM handles it.
--   * Status has 59 NULL/blank rows, all very recent (most within the last
--     month) - these read as genuinely unfinished drafts, not lost history,
--     so they map to a new 'Draft' status rather than staying NULL (NULL
--     would silently break any status filter downstream). Every other legacy
--     status value is preserved as-is: they're already the right shape
--     ('Delivered', 'For Verification', 'Printed', 'Partially Delivered',
--     'For Approval', 'Approved', 'Rejected', 'Paid', 'Created') and this
--     migration does not collapse or reinterpret them - that's a workflow
--     design question for later, not a data-migration one.
--   * SupportingDoc stores the literal string 'NULL' (a PHP string-concat
--     artifact) on rows with no real attachment; treated as actual NULL here.
--     Only the filename is carried over (attachmentPath) - the legacy app's
--     uploaded files themselves are not copied by this script.
--   * created_at/updated_at are DATE-only in the legacy table (no time
--     component survives), so createdAt/updatedAt land at midnight. No more
--     precise data exists to recover.
--   * No column on tbl_new_purchase ever recorded *who* created a PO - only
--     Branch. createdBy/updatedBy are NULL for every migrated row, the same
--     gap already documented for the Fuel PO migration.
--   * 10 POs have a stored TotalSales that doesn't match SUM(line item
--     Amount), and 2 have Vatable+VAT that doesn't match TotalSales - both
--     confirmed present in the raw legacy tables (not introduced by this
--     migration), most likely headers that went stale after their line items
--     were edited post-save, or straight data-entry mistakes on very old
--     rows. Migrated verbatim rather than silently "corrected" - the new PO
--     workflow should compute its own totals from line items going forward
--     rather than trusting a stored header total.
--
--   Line items (tbl_new_poproducts, 14,790 rows):
--   * Catalogue resolves to tbl_inventory_items.catalog for 12,255 of 14,790
--     rows (817 distinct catalog codes across 2,535 rows do not match any
--     current inventory item - likely discontinued items or catalog
--     renumbering over the years). catalogCode/description/unit are copied
--     onto every line regardless of match, for the same "freeze what the PO
--     said" reasoning as the supplier snapshot above.
--   * 5 line items reference a PONumber with no matching header row (deleted
--     or mistyped historically) and are not migrated - there is no PO for
--     them to belong to. That's 5 of 14,790 (0.03%).
--   * UnitCost is VARCHAR and 17 rows have leading non-breaking spaces
--     (U+00A0) ahead of a comma-formatted number, same artifact
--     migrate_suppliers.sql found in tbl_supplier_products.Price - stripped
--     the same way. Quantity and QuantityServed are clean on every row.
--   * `sequence` (order within its PO) does not exist in the source; it's
--     reconstructed here from each line's original auto-increment ID order
--     within its PONumber, using a MySQL 5.7 session-variable running count
--     (this server does not support window functions - MySQL 5.7).
--   * `allocation` is free text of unclear internal meaning (e.g.
--     "PUL-2018-17:PAMANA MEDICAL CENTER->1", possibly a program/grant or
--     consignment placement code) - preserved verbatim, unparsed. Some rows
--     concatenate several such entries with "<br />" up to 615 chars, hence
--     TEXT rather than VARCHAR. Worth asking about before the new PO workflow
--     tries to make use of it.
--   * tbl_new_purchase / tbl_new_poproducts are latin1 while the new tables
--     are utf8mb4, so every cross-database string comparison below explicitly
--     converts + collates to avoid "illegal mix of collations".

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_purchase_orders (
    id INT NOT NULL AUTO_INCREMENT,
    poNumber VARCHAR(20) NOT NULL,
    orderDate DATE NULL,
    supplierId INT NULL,
    supplierName VARCHAR(255) NULL,
    supplierAddress VARCHAR(255) NULL,
    supplierTelephone VARCHAR(100) NULL,
    supplierFax VARCHAR(100) NULL,
    supplierEmail VARCHAR(255) NULL,
    deliveryAddress VARCHAR(255) NULL,
    deliveryTelephone VARCHAR(100) NULL,
    deliveryMobileNumber VARCHAR(100) NULL,
    deliveryTerm VARCHAR(255) NULL,
    paymentTerm VARCHAR(255) NULL,
    deliveryDate DATE NULL,
    paymentDueDate DATE NULL,
    vatableAmount DECIMAL(14,2) NULL,
    vatAmount DECIMAL(14,2) NULL,
    totalAmount DECIMAL(14,2) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Draft',
    noaNumber VARCHAR(255) NULL,
    notes VARCHAR(255) NULL,
    attachmentPath VARCHAR(255) NULL,
    branch VARCHAR(100) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_purchase_orders_poNumber (poNumber),
    KEY idx_tbl_purchase_orders_supplierId (supplierId),
    KEY idx_tbl_purchase_orders_status (status),
    KEY idx_tbl_purchase_orders_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_purchase_orders_supplier
        FOREIGN KEY (supplierId) REFERENCES db_os_2026.tbl_suppliers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_purchase_order_items (
    id INT NOT NULL AUTO_INCREMENT,
    purchaseOrderId INT NOT NULL,
    sequence INT NOT NULL,
    itemId INT NULL,
    catalogCode VARCHAR(50) NULL,
    description VARCHAR(255) NULL,
    unit VARCHAR(30) NULL,
    quantity DECIMAL(12,2) NULL,
    quantityServed DECIMAL(12,2) NOT NULL DEFAULT 0,
    unitCost DECIMAL(12,2) NULL,
    amount DECIMAL(14,2) NULL,
    allocation TEXT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_purchase_order_items_po_sequence (purchaseOrderId, sequence),
    KEY idx_tbl_purchase_order_items_itemId (itemId),
    CONSTRAINT fk_tbl_purchase_order_items_po
        FOREIGN KEY (purchaseOrderId) REFERENCES db_os_2026.tbl_purchase_orders (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_purchase_order_items_item
        FOREIGN KEY (itemId) REFERENCES db_os_2026.tbl_inventory_items (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) PO headers, linked through the new integer supplierId where it resolves.
INSERT INTO db_os_2026.tbl_purchase_orders
    (poNumber, orderDate, supplierId, supplierName, supplierAddress,
     supplierTelephone, supplierFax, supplierEmail,
     deliveryAddress, deliveryTelephone, deliveryMobileNumber,
     deliveryTerm, paymentTerm, deliveryDate, paymentDueDate,
     vatableAmount, vatAmount, totalAmount, status, noaNumber, notes,
     attachmentPath, branch, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    TRIM(p.PONumber),
    p.Date,
    sup.id,
    NULLIF(TRIM(p.Supplier), ''),
    NULLIF(TRIM(p.Address), ''),
    NULLIF(TRIM(p.TelNumber), ''),
    NULLIF(TRIM(p.FaxNumber), ''),
    NULLIF(TRIM(p.Email), ''),
    NULLIF(TRIM(p.DelAddress), ''),
    NULLIF(TRIM(p.DelTelNumber), ''),
    NULLIF(TRIM(p.MobileNumber), ''),
    NULLIF(TRIM(p.DelTerm), ''),
    NULLIF(TRIM(p.PaymentTerm), ''),
    p.DeliveryDate,
    p.PaymentDue,
    CASE WHEN TRIM(COALESCE(p.Vatable, '')) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
         THEN CAST(TRIM(p.Vatable) AS DECIMAL(14,2)) ELSE NULL END,
    CASE WHEN TRIM(COALESCE(p.VAT, '')) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
         THEN CAST(TRIM(p.VAT) AS DECIMAL(14,2)) ELSE NULL END,
    CASE WHEN TRIM(COALESCE(p.TotalSales, '')) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
         THEN CAST(TRIM(p.TotalSales) AS DECIMAL(14,2)) ELSE NULL END,
    COALESCE(NULLIF(TRIM(p.Status), ''), 'Draft'),
    NULLIF(TRIM(p.NOANumber), ''),
    NULLIF(TRIM(p.Notes), ''),
    CASE WHEN TRIM(COALESCE(p.SupportingDoc, '')) IN ('', 'NULL') THEN NULL ELSE TRIM(p.SupportingDoc) END,
    NULLIF(TRIM(p.Branch), ''),
    0, NULL, CAST(p.created_at AS DATETIME), NULL, CAST(p.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_new_purchase p
LEFT JOIN db_os_2026.tbl_suppliers sup
    ON sup.code = CONVERT(TRIM(p.SupplierID) USING utf8mb4) COLLATE utf8mb4_unicode_ci;

-- 2) Line items, linked through the new integer purchaseOrderId/itemId.
--    sequence is reconstructed from each line's original insertion order
--    within its PO (MySQL 5.7 has no window functions, hence the session
--    variables; LIMIT on the derived table prevents the optimizer from
--    merging it away and losing the ORDER BY).
SET @po := '', @seq := 0;

INSERT INTO db_os_2026.tbl_purchase_order_items
    (purchaseOrderId, sequence, itemId, catalogCode, description, unit,
     quantity, quantityServed, unitCost, amount, allocation, createdAt, updatedAt)
SELECT
    po.id,
    ordered.sequence,
    inv.id,
    NULLIF(TRIM(ordered.Catalogue), ''),
    NULLIF(TRIM(ordered.Description), ''),
    NULLIF(TRIM(ordered.Unit), ''),
    CAST(TRIM(REPLACE(ordered.Quantity, ',', '')) AS DECIMAL(12,2)),
    COALESCE(CAST(TRIM(REPLACE(ordered.QuantityServed, ',', '')) AS DECIMAL(12,2)), 0),
    CASE
        WHEN TRIM(REPLACE(REPLACE(ordered.UnitCost, ',', ''), UNHEX('C2A0'), '')) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
        THEN CAST(TRIM(REPLACE(REPLACE(ordered.UnitCost, ',', ''), UNHEX('C2A0'), '')) AS DECIMAL(12,2))
        ELSE NULL
    END,
    ordered.Amount,
    NULLIF(TRIM(ordered.allocation), ''),
    CAST(ordered.created_at AS DATETIME),
    CAST(ordered.updated_at AS DATETIME)
FROM (
    SELECT
        i.*,
        @seq := IF(@po = i.PONumber, @seq + 1, 1) AS sequence,
        @po := i.PONumber AS _po_marker
    FROM db_oams_app_2026.tbl_new_poproducts i
    ORDER BY i.PONumber, i.ID
    LIMIT 18446744073709551615
) ordered
JOIN db_os_2026.tbl_purchase_orders po
    ON po.poNumber = CONVERT(ordered.PONumber USING utf8mb4) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_inventory_items inv
    ON inv.catalog = CONVERT(TRIM(ordered.Catalogue) USING utf8mb4) COLLATE utf8mb4_unicode_ci
   AND inv.isDeleted = 0;
