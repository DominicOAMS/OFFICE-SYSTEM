-- Migration: db_oams_app_2026.tbl_account_payables -> db_os_2026.tbl_account_payables
--
-- This is the "amount owed to a supplier for a delivered PO" ledger (and, going forward,
-- also non-PO bills - see notes below). Not to be confused with the new tbl_check_vouchers
-- (the actual payment/check record) migrated separately in migrate_check_vouchers.sql.
--
-- Notes on the source data (profiled before writing this):
--   * id reuses the legacy APID directly (like tbl_warehouse_transactions reused transID) -
--     it's already a clean sequential int with no non-numeric values to work around, unlike
--     tbl_invoices' fresh-surrogate approach. AUTO_INCREMENT is reset to 1258 afterward so
--     new payables continue the same sequence.
--   * PONumber resolves to tbl_purchase_orders.poNumber for 1,257 of 1,257 rows (100%), and
--     every one of those resolved POs already has a non-NULL supplierId - so supplierId is
--     NOT NULL here. Every payable, PO or Non-PO, is owed to a known supplier; a non-PO bill
--     (rent, utilities) just means adding that payee as a Supplier record too, reusing the
--     module that already exists rather than inventing a second payee concept.
--   * tbl_account_payables itself never stored the supplier's name/address/TIN - only
--     PONumber/SINumber/DRNumber. payeeName/payeeAddress/payeeTin are therefore snapshotted
--     from the resolved supplier's CURRENT record (not a live join going forward - this
--     migration runs once), same "freeze what it said" reasoning as every other snapshot in
--     this project, just sourced from the supplier table since the legacy row itself never
--     captured this text.
--   * Status is only ever 'Verified' or 'Paid' (1,255 / 2 rows) - both map verbatim to the
--     new workflow's vocabulary, no renaming needed.
--   * VerifiedBy is a free-text name ('Beatrice Martin', etc.), not a user id. Matches
--     tbl_users.name for 963 of 1,257 rows (77%) - resolved into a real verifiedBy FK where
--     it matches. The raw text is kept in legacyVerifiedByName regardless of match (same
--     "snapshot regardless of FK match" rule as every supplier/customer name elsewhere), so
--     the 294 unmatched names aren't silently lost.
--   * verifiedAt has no dedicated legacy column - proxied as updated_at (the row's last
--     touch), since every row is already Verified/Paid by the time it was dumped and no more
--     precise moment exists to recover.
--   * Legacy only stored Amount + EWT (EWTType is the rate, e.g. '0.01'; EWT is the computed
--     peso amount) - no Vatable/VAT split existed on this table at all (unlike the voucher
--     table). vatableAmount/vatAmount are computed fresh here via the standard 12% VAT
--     back-out (amount / 1.12) - confirmed against the data that EWT / Amount ~= 0.0089,
--     which is exactly (1/1.12) * 0.01, i.e. EWT is computed on the net-of-VAT base. EWTType/
--     EWT themselves are copied as-is into ewtRate/ewtAmount rather than recomputed, since
--     they already are the stored, correct value.
--   * ReferenceNumber is a distinct-per-row internal ledger number (10-5444, 1,256 distinct
--     across 1,257 rows) unrelated to any other table - kept as free text.
--   * created_at/updated_at are VARCHAR on the legacy table (a full "YYYY-MM-DD HH:MM:SS"
--     string in every sampled row), hence the CAST(... AS DATETIME).
--   * No column on the legacy table ever recorded *who* created a payable row (only who
--     verified it) - createdBy is NULL for every migrated row, the same gap already
--     documented for Fuel PO/Purchase Orders.
--   * tbl_account_payables (legacy) is already utf8mb4 (unlike tbl_new_purchase, which was
--     latin1) - COLLATE utf8mb4_unicode_ci is enough for the cross-database join, no CONVERT
--     needed.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_account_payables (
    id INT NOT NULL AUTO_INCREMENT,
    purchaseOrderId INT NULL,
    poNumber VARCHAR(20) NULL,
    supplierId INT NOT NULL,
    payeeName VARCHAR(255) NULL,
    payeeAddress VARCHAR(255) NULL,
    payeeTin VARCHAR(255) NULL,
    siNumber VARCHAR(255) NULL,
    drNumber VARCHAR(255) NULL,
    referenceNumber VARCHAR(255) NULL,
    description TEXT NULL,
    amount DECIMAL(14,2) NOT NULL,
    ewtRate DECIMAL(6,4) NOT NULL DEFAULT 0.0100,
    ewtAmount DECIMAL(14,2) NOT NULL,
    vatableAmount DECIMAL(14,2) NOT NULL,
    vatAmount DECIMAL(14,2) NOT NULL,
    netAmount DECIMAL(14,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Created',
    verifiedBy INT NULL,
    verifiedAt DATETIME NULL,
    legacyVerifiedByName VARCHAR(255) NULL,
    voidedBy INT NULL,
    voidedAt DATETIME NULL,
    voidReason VARCHAR(255) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_account_payables_purchaseOrderId (purchaseOrderId),
    KEY idx_tbl_account_payables_supplierId (supplierId),
    KEY idx_tbl_account_payables_status (status),
    KEY idx_tbl_account_payables_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_account_payables_po
        FOREIGN KEY (purchaseOrderId) REFERENCES db_os_2026.tbl_purchase_orders (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_account_payables_supplier
        FOREIGN KEY (supplierId) REFERENCES db_os_2026.tbl_suppliers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_account_payables_verifiedBy
        FOREIGN KEY (verifiedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_account_payables_voidedBy
        FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_account_payables
    (id, purchaseOrderId, poNumber, supplierId, payeeName, payeeAddress, payeeTin,
     siNumber, drNumber, referenceNumber, amount, ewtRate, ewtAmount,
     vatableAmount, vatAmount, netAmount, status, verifiedBy, verifiedAt,
     legacyVerifiedByName, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    ap.APID,
    po.id,
    TRIM(ap.PONumber),
    sup.id,
    sup.name,
    sup.address,
    sup.tin,
    NULLIF(TRIM(ap.SINumber), ''),
    NULLIF(TRIM(ap.DRNumber), ''),
    NULLIF(TRIM(ap.ReferenceNumber), ''),
    CAST(ap.Amount AS DECIMAL(14,2)),
    CAST(ap.EWTType AS DECIMAL(6,4)),
    CAST(ap.EWT AS DECIMAL(14,2)),
    ROUND(CAST(ap.Amount AS DECIMAL(14,2)) / 1.12, 2),
    CAST(ap.Amount AS DECIMAL(14,2)) - ROUND(CAST(ap.Amount AS DECIMAL(14,2)) / 1.12, 2),
    CAST(ap.Amount AS DECIMAL(14,2)) - CAST(ap.EWT AS DECIMAL(14,2)),
    TRIM(ap.Status),
    usr.id,
    CAST(ap.updated_at AS DATETIME),
    NULLIF(TRIM(ap.VerifiedBy), ''),
    0, NULL, CAST(ap.created_at AS DATETIME), NULL, CAST(ap.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_account_payables ap
JOIN db_os_2026.tbl_purchase_orders po
    ON po.poNumber = TRIM(ap.PONumber) COLLATE utf8mb4_unicode_ci
JOIN db_os_2026.tbl_suppliers sup
    ON sup.id = po.supplierId
LEFT JOIN db_os_2026.tbl_users usr
    ON usr.name = TRIM(ap.VerifiedBy) COLLATE utf8mb4_unicode_ci;

ALTER TABLE db_os_2026.tbl_account_payables AUTO_INCREMENT = 1258;
