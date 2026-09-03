-- Migration: db_oams_app_2026.tbl_collection -> db_os_2026.tbl_collections
--         + a new (empty here) db_os_2026.tbl_collection_invoices junction table
--
-- This is the payment side of Receivables - a customer's Official Receipt applied against
-- one or more invoices. Invoices themselves are already the "amount owed" ledger (this
-- module doesn't need a fresh one the way Payables needed tbl_account_payables - it already
-- exists). The comma-separated Invoices reference field is NOT parsed here - MySQL 5.7 has
-- no clean way to split a variable-length comma list into rows without a tally-table hack,
-- so that pass (and the resulting invoice-status cascade) is done in
-- migrate_collection_invoices.py instead, which must run AFTER this file.
--
-- Notes on the source data (profiled before writing this):
--   * id is a fresh surrogate, NOT a reuse of legacy ORNumber the way Warehouse Transactions
--     reused transID. An OR number is a physical pre-printed booklet number a field
--     collector already holds (see BookletNumber/SeriesNumber) - it's not a
--     software-generated sequence, so it doesn't belong as a PK any more than invoiceNumber
--     does. orNumber is kept as a separate UNIQUE business-key column instead (confirmed
--     1,667 of 1,667 unique in the source, no duplicates).
--   * HospitalID resolves to tbl_customers.code for 1,656 of 1,667 rows (99.3%). The 11
--     unmatched rows all have a NULL HospitalID in the source itself (not a bad/mistyped
--     code) - some still carry a Hospital name with no ID at all, so customerId is nullable
--     here (unlike Payables' supplierId, which had zero unresolved rows). customerCode/
--     customerName are snapshotted from the legacy row's OWN HospitalID/Hospital text
--     regardless of match - this table already recorded that text itself, so "freeze what
--     it said" means keeping what THIS document said, not a live join to the customer's
--     current record.
--   * WithBIRForm is a real three-valued field (Yes / No / To Follow) once cleaned up - raw
--     values include whitespace-padded variants (' Yes         ') and a literal string
--     'NULL' (a PHP artifact, treated as real NULL here), both TRIM'd away.
--   * Legacy only stored WTax as a peso amount, no separate rate column - wtaxRate is
--     derived here as WTax / (Amount / 1.12) (the same net-of-VAT EWT base as Payables),
--     guarded to 0 when Amount or WTax is 0 rather than defaulting to a rate that was never
--     actually applied. Confirmed against the data: this ratio is ~0.01 (1%) on almost every
--     row, with at least one real outlier around 5.7%, confirming it's a genuine editable
--     rate rather than always exactly 1%.
--   * Retention mixes what look like fractional values (0, 0.05, 1) and full peso amounts
--     (984, 9526) with no second column to cross-check which is which - migrated verbatim as
--     a plain numeric amount, not reinterpreted, same as every other migration's stance on
--     an ambiguous legacy column.
--   * netAmount = amount - wtaxAmount - retentionAmount (what was actually banked) is
--     computed fresh here since legacy never stored it at all.
--   * DateCollected/ChequeDate get the same REGEXP-validate-then-NULL treatment as every
--     other migration's dirty dates (22 bad/null DateCollected, 12 bad ChequeDate out of
--     1,667 - a small, expected fraction, same class as every prior migration's date
--     cleanup).
--   * created_at/updated_at are VARCHAR on the legacy table (same as tbl_account_payables
--     was), hence the CAST(... AS DATETIME).
--   * No column on the legacy table ever recorded *who* entered a collection into the system
--     (CollectedBy is the field collector, a different real-world person) - createdBy is
--     NULL for every migrated row, the same gap already documented for Fuel PO/Purchase
--     Orders/Payables.
--   * tbl_collection (legacy) is already utf8mb4 - COLLATE utf8mb4_unicode_ci is enough for
--     the cross-database join, no CONVERT needed.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_collections (
    id INT NOT NULL AUTO_INCREMENT,
    orNumber INT NOT NULL,
    customerId INT NULL,
    customerCode VARCHAR(50) NULL,
    customerName VARCHAR(255) NULL,
    dateCollected DATE NULL,
    collectedBy VARCHAR(255) NULL,
    remittedTo VARCHAR(255) NULL,
    chequeNumber VARCHAR(100) NULL,
    chequeDate DATE NULL,
    bank VARCHAR(100) NULL,
    bookletNumber VARCHAR(50) NULL,
    seriesNumber VARCHAR(50) NULL,
    amount DECIMAL(14,2) NOT NULL,
    wtaxRate DECIMAL(6,4) NOT NULL DEFAULT 0.0100,
    wtaxAmount DECIMAL(14,2) NOT NULL DEFAULT 0,
    retentionAmount DECIMAL(14,2) NOT NULL DEFAULT 0,
    netAmount DECIMAL(14,2) NOT NULL,
    birFormStatus VARCHAR(20) NULL,
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
    UNIQUE KEY uq_tbl_collections_orNumber (orNumber),
    KEY idx_tbl_collections_customerId (customerId),
    KEY idx_tbl_collections_status (status),
    KEY idx_tbl_collections_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_collections_customer
        FOREIGN KEY (customerId) REFERENCES db_os_2026.tbl_customers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_collections_voidedBy
        FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_collection_invoices (
    id INT NOT NULL AUTO_INCREMENT,
    collectionId INT NOT NULL,
    invoiceId INT NOT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_collection_invoices (collectionId, invoiceId),
    KEY idx_tbl_collection_invoices_invoiceId (invoiceId),
    CONSTRAINT fk_tbl_collection_invoices_collection
        FOREIGN KEY (collectionId) REFERENCES db_os_2026.tbl_collections (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_collection_invoices_invoice
        FOREIGN KEY (invoiceId) REFERENCES db_os_2026.tbl_invoices (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_collections
    (orNumber, customerId, customerCode, customerName, dateCollected, collectedBy,
     remittedTo, chequeNumber, chequeDate, bank, bookletNumber, seriesNumber,
     amount, wtaxRate, wtaxAmount, retentionAmount, netAmount, birFormStatus, notes,
     status, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    col.ORNumber,
    cust.id,
    NULLIF(TRIM(col.HospitalID), ''),
    NULLIF(TRIM(col.Hospital), ''),
    -- Money already received can't be dated in the future, unlike ChequeDate below
    -- (a post-dated check is a real, legitimate practice) - hence the tighter upper bound.
    CASE WHEN col.DateCollected REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
              AND col.DateCollected BETWEEN '2015-01-01' AND CURDATE()
         THEN col.DateCollected ELSE NULL END,
    NULLIF(TRIM(col.CollectedBy), ''),
    NULLIF(TRIM(col.RemittedTo), ''),
    NULLIF(TRIM(col.ChequeNumber), ''),
    CASE WHEN col.ChequeDate REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
              AND col.ChequeDate BETWEEN '2015-01-01' AND '2027-01-01'
         THEN col.ChequeDate ELSE NULL END,
    NULLIF(TRIM(col.Bank), ''),
    NULLIF(TRIM(col.BookletNumber), ''),
    NULLIF(TRIM(col.SeriesNumber), ''),
    CAST(col.Amount AS DECIMAL(14,2)),
    CASE WHEN col.Amount > 0 AND COALESCE(col.WTax, 0) > 0
         THEN ROUND(COALESCE(col.WTax, 0) / (col.Amount / 1.12), 4)
         ELSE 0 END,
    CAST(COALESCE(col.WTax, 0) AS DECIMAL(14,2)),
    CASE WHEN TRIM(COALESCE(col.Retention, '')) REGEXP '^[0-9]+(\\.[0-9]+)?$'
         THEN CAST(TRIM(col.Retention) AS DECIMAL(14,2)) ELSE 0 END,
    CAST(col.Amount AS DECIMAL(14,2)) - CAST(COALESCE(col.WTax, 0) AS DECIMAL(14,2))
        - (CASE WHEN TRIM(COALESCE(col.Retention, '')) REGEXP '^[0-9]+(\\.[0-9]+)?$'
                THEN CAST(TRIM(col.Retention) AS DECIMAL(14,2)) ELSE 0 END),
    CASE
        WHEN TRIM(COALESCE(col.WithBIRForm, '')) = 'Yes' THEN 'Yes'
        WHEN TRIM(COALESCE(col.WithBIRForm, '')) = 'No' THEN 'No'
        WHEN TRIM(COALESCE(col.WithBIRForm, '')) = 'To Follow' THEN 'To Follow'
        ELSE NULL
    END,
    NULLIF(TRIM(col.Notes), ''),
    'Created',
    0, NULL, CAST(col.created_at AS DATETIME), NULL, CAST(col.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_collection col
LEFT JOIN db_os_2026.tbl_customers cust
    ON cust.code = TRIM(col.HospitalID) COLLATE utf8mb4_unicode_ci;
