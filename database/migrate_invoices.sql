-- Migration: db_oams_app_2026.tbl_new_invoice / tbl_new_invoicedetails
--         -> db_os_2026.tbl_invoices / tbl_invoice_items
--
-- Follows the same shape as migrate_warehouse_transactions.sql / migrate_purchase_orders.sql.
--
-- Notes on the source data (profiled before writing this):
--   * InvoiceNum is NOT reused as `id` the way transID was for Warehouse Transactions - one
--     legacy value ("0207925-CM", a credit-memo variant, status='Returned', negative amounts)
--     isn't an integer, and the zero-padding in normal numbers ("0207502") is semantically
--     part of the printed invoice number, so it has to survive as text regardless. `id` is a
--     fresh AUTO_INCREMENT surrogate; `invoiceNumber` (UNIQUE) holds the preserved string -
--     same shape tbl_purchase_orders already uses (id + separate poNumber).
--   * CustomerID resolves to db_os_2026.tbl_customers.code for 8,090 of 8,095 rows once
--     trimmed (99.94%) - the other 5 (4 distinct codes: 'PBI-2023-41', 'PCA-2023-67', '55',
--     '51') are either since-renamed/deleted customers or legacy bare-numeric codes (the same
--     pattern customers_repo.next_customer_id_number() already documents as pre-existing
--     legacy noise). customerId is left NULL for those; customerCode keeps the raw trimmed
--     text regardless of match, same "freeze what it said" treatment used everywhere else.
--   * PONum is the CUSTOMER's own PO reference, confirmed by sampling (values don't correlate
--     with tbl_purchase_orders.poNumber at all) - migrated as `customerPo`, matching the field
--     name tbl_warehouse_transactions already uses for this exact concept. Naming it
--     `poNumber` here would collide in meaning with that column elsewhere in the schema.
--   * Vatable is a peso amount (the taxable sales total), not a boolean despite the name.
--     Confirmed VAT-INCLUSIVE pricing: SUM(line Amount) per invoice equals AmountDue, not
--     Vatable - i.e. Vatable is back-calculated as AmountDue / 1.12. Migrated as-is
--     (vatableAmount/vatAmount/totalAmount); the new module recomputes these from line items
--     on every create/edit rather than trusting stored totals, but historical values are kept
--     verbatim here since they're already internally consistent (Vatable + VAT = AmountDue on
--     every sampled row).
--   * Status is migrated verbatim except 'Voided' -> 'Void' (371 rows - same state, different
--     spelling; left as 'Voided' it would silently miss the new module's Void filter). The 9
--     legacy 'Finished' and 1 'Returned' rows are NOT reinterpreted - they migrate as-is and
--     simply won't match any of the new module's status-transition rules (View only), same
--     "nothing here needs reinterpreting" stance migrate_warehouse_transactions.sql took.
--   * BusinessType, OscaPwdIdNum, ScPwdSignature, and legacy DeliveredBy are NULL/blank on all
--     8,095 rows and are not migrated - same call made for other always-blank legacy columns.
--     (The new `deliveredBy` INT column added below is unrelated - it's a fresh workflow
--     column for the Deliver action, not a mapping of the legacy text column of the same name.)
--   * created_at/updated_at are NULL on 388 header rows and 1,101 detail rows (never populated
--     by the legacy app for those). Header rows fall back to InvoiceDate (always populated,
--     just the date, not a real timestamp - the best available signal); detail rows fall back
--     to their parent invoice's own created_at, same as the 34 warehouse-transaction-item rows
--     migrate_warehouse_transactions.sql handled the same way.
--   * tbl_new_invoice / tbl_new_invoicedetails are utf8mb4_general_ci while the new tables are
--     utf8mb4_unicode_ci (both already utf8mb4, so COLLATE alone is enough, no CONVERT needed -
--     same situation migrate_warehouse_transactions.sql had with tbl_transaction).
--
--   Line items (tbl_new_invoicedetails, 26,849 rows):
--   * ProductCatalog resolves to tbl_inventory_items.catalog for ~98.75% of rows (336 don't
--     match) - catalogCode/description/unit/category are copied onto every line regardless of
--     match, same "freeze what it said" reasoning as every other line-item migration here.
--   * 4 line items reference an InvoiceNum with no matching header row and are not migrated -
--     0.015%, same class as every other migration's orphan rate.
--   * Category is clean (only 'VITROS' / 'Other Products' across all rows). Quantity ranges
--     0-8000; the single Quantity=0 row is a genuine zero-quantity line, kept as-is (same
--     treatment the 9 zero-quantity warehouse-transaction lines got).
--   * Expiry is VARCHAR; 12 rows aren't well-formed YYYY-MM-DD and become NULL.
--   * UnitPrice is VARCHAR; 12 rows have comma-formatted numbers ("1,096.00") that are
--     stripped before casting. Exactly one row (ItemNum 4016) is genuinely malformed
--     ("985.6-0", a stray data-entry typo) - hardcoded below to its correct value, recovered
--     as Amount/Quantity (1971.20 / 2 = 985.60) for that ONE row specifically, not as a
--     generic fallback formula (a generic Amount/Quantity fallback would divide by zero on
--     the legitimate Quantity=0 row elsewhere).
--   * FOC is 0 on all 26,849 rows and is not migrated.
--   * enteredQuantity/enteredPackSize (the pack-size feature's snapshot columns, already
--     built for Warehouse Transactions) are included from the start here rather than bolted
--     on later: enteredQuantity = Quantity, enteredPackSize = NULL for every migrated row,
--     meaning "entered directly in base units" - the same backfill semantics used when the
--     pack-size feature was added to tbl_warehouse_transaction_items.
--   * `sequence` (order within its invoice) does not exist in the source; reconstructed from
--     each line's original auto-increment order within its InvoiceNum, using the same MySQL
--     5.7 session-variable running-count trick migrate_warehouse_transactions.sql used (this
--     server has no window functions). InvoiceNum is a string here (not castable to an int,
--     because of the "-CM" row), so the partition comparison uses BINARY to avoid any
--     collation surprises.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_invoices (
    id INT NOT NULL AUTO_INCREMENT,
    invoiceNumber VARCHAR(20) NOT NULL,
    invoiceDate DATE NULL,
    customerId INT NULL,
    customerCode VARCHAR(20) NULL,
    soldTo VARCHAR(255) NULL,
    address VARCHAR(255) NULL,
    tin VARCHAR(30) NULL,
    customerPo VARCHAR(100) NULL,
    paymentTerms VARCHAR(100) NULL,
    paymentDueDate DATE NULL,
    salesPerson VARCHAR(100) NULL,
    vatableAmount DECIMAL(14,2) NULL,
    vatAmount DECIMAL(14,2) NULL,
    totalAmount DECIMAL(14,2) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Created',
    invoiceType VARCHAR(30) NULL,
    noaNumber VARCHAR(30) NULL,
    notes TEXT NULL,
    branch VARCHAR(100) NULL,
    printedBy INT NULL,
    printedAt DATETIME NULL,
    deliveredBy INT NULL,
    deliveredAt DATETIME NULL,
    paidBy INT NULL,
    paidAt DATETIME NULL,
    voidedBy INT NULL,
    voidedAt DATETIME NULL,
    voidReason VARCHAR(255) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_invoices_invoiceNumber (invoiceNumber),
    KEY idx_tbl_invoices_customerId (customerId),
    KEY idx_tbl_invoices_status (status),
    KEY idx_tbl_invoices_isDeleted (isDeleted),
    KEY idx_tbl_invoices_invoiceDate (invoiceDate),
    CONSTRAINT fk_tbl_invoices_customer
        FOREIGN KEY (customerId) REFERENCES db_os_2026.tbl_customers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_invoice_items (
    id INT NOT NULL AUTO_INCREMENT,
    invoiceId INT NOT NULL,
    sequence INT NOT NULL,
    itemId INT NULL,
    catalogCode VARCHAR(50) NULL,
    description TEXT NULL,
    unit VARCHAR(30) NULL,
    category VARCHAR(50) NULL,
    quantity INT NULL,
    enteredQuantity INT NULL,
    enteredPackSize INT NULL,
    lot VARCHAR(50) NULL,
    expiryDate DATE NULL,
    unitPrice DECIMAL(12,2) NULL,
    amount DECIMAL(14,2) NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_invoice_items_invoice_sequence (invoiceId, sequence),
    KEY idx_tbl_invoice_items_itemId (itemId),
    CONSTRAINT fk_tbl_invoice_items_invoice
        FOREIGN KEY (invoiceId) REFERENCES db_os_2026.tbl_invoices (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_invoice_items_item
        FOREIGN KEY (itemId) REFERENCES db_os_2026.tbl_inventory_items (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) Invoice headers.
INSERT INTO db_os_2026.tbl_invoices
    (invoiceNumber, invoiceDate, customerId, customerCode, soldTo, address, tin,
     customerPo, paymentTerms, paymentDueDate, salesPerson,
     vatableAmount, vatAmount, totalAmount, status, invoiceType, noaNumber, notes, branch,
     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    TRIM(inv.InvoiceNum),
    inv.InvoiceDate,
    c.id,
    NULLIF(TRIM(inv.CustomerID), ''),
    NULLIF(TRIM(inv.SoldTo), ''),
    NULLIF(TRIM(inv.Address), ''),
    NULLIF(TRIM(inv.TIN), ''),
    NULLIF(TRIM(inv.PONum), ''),
    NULLIF(TRIM(inv.PaymentTerms), ''),
    inv.PaymentDueDate,
    NULLIF(TRIM(inv.SalesPerson), ''),
    CAST(inv.Vatable AS DECIMAL(14,2)),
    CAST(inv.VAT AS DECIMAL(14,2)),
    CAST(inv.AmountDue AS DECIMAL(14,2)),
    CASE
        WHEN TRIM(inv.Status) = 'Voided' THEN 'Void'
        ELSE COALESCE(NULLIF(TRIM(inv.Status), ''), 'Created')
    END,
    NULLIF(TRIM(inv.InvoiceType), ''),
    NULLIF(TRIM(inv.NOANumber), ''),
    NULLIF(TRIM(inv.Notes), ''),
    NULLIF(TRIM(inv.Branch), ''),
    0, NULL,
    COALESCE(inv.created_at, CAST(inv.InvoiceDate AS DATETIME)),
    NULL,
    COALESCE(inv.updated_at, CAST(inv.InvoiceDate AS DATETIME))
FROM db_oams_app_2026.tbl_new_invoice inv
LEFT JOIN db_os_2026.tbl_customers c
    ON c.code = TRIM(inv.CustomerID) COLLATE utf8mb4_unicode_ci;

-- 2) Line items, linked through the new integer invoiceId/itemId. sequence is reconstructed
--    from each line's original insertion order within its InvoiceNum (see header note).
SET @inv := '', @seq := 0;

INSERT INTO db_os_2026.tbl_invoice_items
    (invoiceId, sequence, itemId, catalogCode, description, unit, category,
     quantity, enteredQuantity, enteredPackSize, lot, expiryDate, unitPrice, amount,
     createdAt, updatedAt)
SELECT
    i.id,
    ordered.sequence,
    inv.id,
    NULLIF(TRIM(ordered.ProductCatalog), ''),
    NULLIF(TRIM(ordered.Description), ''),
    NULLIF(TRIM(ordered.Unit), ''),
    NULLIF(TRIM(ordered.Category), ''),
    ordered.Quantity,
    ordered.Quantity,
    NULL,
    NULLIF(TRIM(ordered.LotNumber), ''),
    CASE WHEN ordered.Expiry REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN ordered.Expiry ELSE NULL END,
    CASE
        WHEN ordered.ItemNum = 4016 THEN 985.60
        WHEN TRIM(REPLACE(ordered.UnitPrice, ',', '')) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
            THEN CAST(REPLACE(TRIM(ordered.UnitPrice), ',', '') AS DECIMAL(12,2))
        ELSE NULL
    END,
    CAST(ordered.Amount AS DECIMAL(14,2)),
    COALESCE(ordered.created_at, i.createdAt),
    COALESCE(ordered.updated_at, i.createdAt)
FROM (
    SELECT
        d.ItemNum, d.InvoiceNum, d.ProductCatalog, d.Description, d.Unit, d.Category,
        d.Quantity, d.LotNumber, d.Expiry, d.UnitPrice, d.Amount, d.created_at, d.updated_at,
        @seq := IF(@inv = BINARY d.InvoiceNum, @seq + 1, 1) AS sequence,
        @inv := BINARY d.InvoiceNum AS _inv_marker
    FROM db_oams_app_2026.tbl_new_invoicedetails d
    ORDER BY d.InvoiceNum, d.ItemNum
    LIMIT 18446744073709551615
) ordered
JOIN db_os_2026.tbl_invoices i ON i.invoiceNumber = TRIM(ordered.InvoiceNum) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_inventory_items inv
    ON inv.catalog = TRIM(ordered.ProductCatalog) COLLATE utf8mb4_unicode_ci
   AND inv.isDeleted = 0;
