-- Migration: db_oams_app_2026.tbl_payable_voucher -> db_os_2026.tbl_check_vouchers
--         + a new (empty) db_os_2026.tbl_check_voucher_payables junction table
--
-- This is the actual check-payment record (Prepared -> Checked -> Approved -> Paid). Not to
-- be confused with tbl_account_payables (the "amount owed" ledger it pays off), migrated
-- separately in migrate_payables.sql, which must run BEFORE this file (this migration's
-- CheckedBy/PreparedBy user-name resolution reuses the same tbl_users join approach, and the
-- junction table's FK points at tbl_account_payables).
--
-- Notes on the source data (profiled before writing this):
--   * Legacy has no usable business-facing voucher number at all - CheckID (the obvious
--     candidate) is blank on all 65 rows. voucherNumber is synthesized fresh here as
--     CV-YYYY-NNNN, numbered chronologically by VoucherDate within each year (MySQL 5.7 has
--     no window functions, hence the session-variable running count, same trick every prior
--     migration on this server has used for reconstructing a sequence). This is chosen so a
--     NEW voucher's number (generated the same way, MAX+1 for its year) continues seamlessly
--     from wherever the migrated rows leave off, rather than colliding with them.
--   * PayeeID resolves to tbl_suppliers.code for 65 of 65 rows (100%). payeeName/
--     payeeAddress/payeeTin are snapshotted from the legacy row's OWN Payee/Address/TIN text
--     (not a live join to the supplier's current record) - this table already recorded that
--     text itself at voucher-preparation time, so "freeze what it said" means preserving
--     what THIS document said, the same as every PO/invoice snapshot elsewhere.
--   * Type is 'Goods' on all 65 rows - zero information, not migrated (same call as every
--     other 100%-constant or 100%-blank legacy column across this project).
--   * Status is only ever 'Checked' (2 rows) or 'Approved' (63 rows) - both map verbatim to
--     the new 4-stage vocabulary. Deliberately NOT reinterpreted as 'Paid', even though every
--     one of these vouchers is from 2025-2026 and almost certainly settled in reality -
--     ReceivedBy and CheckID (the only signals that would prove a check was actually
--     released) are 100% blank, so guessing would misstate history. Practical consequence:
--     all 65 rows land in the new workflow's actionable "pending release" state rather than
--     a terminal one.
--   * Legacy already stores Vatable/VAT/EWT/NetTotal as their own columns (unlike
--     tbl_account_payables, which only had Amount+EWT) - copied as-is rather than
--     recomputed, since they're already the correct stored values. NetTotal is VARCHAR
--     (e.g. '6739.2857') - CAST handles the 2-decimal rounding.
--   * PreparedBy is 100% filled ('System Generated' or a real name) - kept verbatim in
--     legacyPreparedByName since it's rarely a real accountable person and createdBy has
--     nothing reliable to resolve against. CheckedBy is filled on only 2 of 65 rows, but
--     where present it IS a real staff name - attempted a tbl_users.name match for those two
--     specifically, same reasoning as VerifiedBy's resolution in migrate_payables.sql.
--     ApprovedBy/ReceivedBy/CheckID are 100% blank and not migrated at all.
--   * checkedAt/approvedAt have no dedicated legacy columns - proxied as updated_at, same
--     "last touch" reasoning as verifiedAt in migrate_payables.sql. checkedAt is set whenever
--     status reached Checked OR Approved (Approved implies Checked already happened);
--     approvedAt only when status is Approved.
--   * tbl_payable_voucher (legacy) is already utf8mb4 - COLLATE utf8mb4_unicode_ci is enough
--     for the cross-database join, no CONVERT needed.
--
--   No junction rows (tbl_check_voucher_payables) are created for any migrated voucher: the
--   legacy schema never stored which specific payables a voucher covered, and reconstructing
--   it from an amount match alone would be guessing at history, not migrating it - same
--   "drop, don't patch" stance as every other unreconstructable relationship this project has
--   hit. Historical vouchers show 0 linked payables in the new UI; only vouchers created
--   going forward get real junction rows.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_check_vouchers (
    id INT NOT NULL AUTO_INCREMENT,
    voucherNumber VARCHAR(20) NOT NULL,
    supplierId INT NOT NULL,
    payeeName VARCHAR(255) NULL,
    payeeAddress TEXT NULL,
    payeeTin VARCHAR(255) NULL,
    voucherDate DATE NULL,
    dueDate DATE NULL,
    totalAmount DECIMAL(14,2) NOT NULL,
    vatableAmount DECIMAL(14,2) NOT NULL,
    vatAmount DECIMAL(14,2) NOT NULL,
    totalEwtAmount DECIMAL(14,2) NOT NULL,
    netAmount DECIMAL(14,2) NOT NULL,
    remarksHeading VARCHAR(255) NULL,
    remarks TEXT NULL,
    checkNumber VARCHAR(255) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Prepared',
    checkedBy INT NULL,
    checkedAt DATETIME NULL,
    approvedBy INT NULL,
    approvedAt DATETIME NULL,
    paidBy INT NULL,
    paidAt DATETIME NULL,
    voidedBy INT NULL,
    voidedAt DATETIME NULL,
    voidReason VARCHAR(255) NULL,
    legacyPreparedByName VARCHAR(255) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_check_vouchers_voucherNumber (voucherNumber),
    KEY idx_tbl_check_vouchers_supplierId (supplierId),
    KEY idx_tbl_check_vouchers_status (status),
    KEY idx_tbl_check_vouchers_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_check_vouchers_supplier
        FOREIGN KEY (supplierId) REFERENCES db_os_2026.tbl_suppliers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_check_vouchers_checkedBy
        FOREIGN KEY (checkedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_check_vouchers_approvedBy
        FOREIGN KEY (approvedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_check_vouchers_paidBy
        FOREIGN KEY (paidBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_check_vouchers_voidedBy
        FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_check_voucher_payables (
    id INT NOT NULL AUTO_INCREMENT,
    voucherId INT NOT NULL,
    payableId INT NOT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_check_voucher_payables (voucherId, payableId),
    KEY idx_tbl_check_voucher_payables_payableId (payableId),
    CONSTRAINT fk_tbl_check_voucher_payables_voucher
        FOREIGN KEY (voucherId) REFERENCES db_os_2026.tbl_check_vouchers (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_check_voucher_payables_payable
        FOREIGN KEY (payableId) REFERENCES db_os_2026.tbl_account_payables (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @vyear := '', @vseq := 0;

INSERT INTO db_os_2026.tbl_check_vouchers
    (voucherNumber, supplierId, payeeName, payeeAddress, payeeTin, voucherDate, dueDate,
     totalAmount, vatableAmount, vatAmount, totalEwtAmount, netAmount,
     remarksHeading, remarks, status, checkedBy, checkedAt, approvedAt,
     legacyPreparedByName, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    CONCAT('CV-', ordered.vyear, '-', LPAD(ordered.vseq, 4, '0')),
    sup.id,
    NULLIF(TRIM(ordered.Payee), ''),
    NULLIF(TRIM(ordered.Address), ''),
    NULLIF(TRIM(ordered.TIN), ''),
    ordered.VoucherDate,
    ordered.DueDate,
    CAST(ordered.Total AS DECIMAL(14,2)),
    CAST(ordered.Vatable AS DECIMAL(14,2)),
    CAST(ordered.VAT AS DECIMAL(14,2)),
    CAST(ordered.EWT AS DECIMAL(14,2)),
    CAST(REPLACE(ordered.NetTotal, ',', '') AS DECIMAL(14,2)),
    NULLIF(TRIM(ordered.RemarksHeading), ''),
    NULLIF(TRIM(ordered.Remarks), ''),
    TRIM(ordered.Status),
    cb.id,
    CASE WHEN TRIM(ordered.Status) IN ('Checked', 'Approved')
         THEN CAST(ordered.updated_at AS DATETIME) ELSE NULL END,
    CASE WHEN TRIM(ordered.Status) = 'Approved'
         THEN CAST(ordered.updated_at AS DATETIME) ELSE NULL END,
    NULLIF(TRIM(ordered.PreparedBy), ''),
    0, NULL, CAST(ordered.created_at AS DATETIME), NULL, CAST(ordered.updated_at AS DATETIME)
FROM (
    SELECT
        v.*,
        @vseq := IF(@vyear = YEAR(v.VoucherDate), @vseq + 1, 1) AS vseq,
        @vyear := YEAR(v.VoucherDate) AS vyear
    FROM db_oams_app_2026.tbl_payable_voucher v
    ORDER BY YEAR(v.VoucherDate), v.VoucherDate, v.ID
    LIMIT 18446744073709551615
) ordered
JOIN db_os_2026.tbl_suppliers sup
    ON sup.code = TRIM(ordered.PayeeID) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_users cb
    ON cb.name = TRIM(ordered.CheckedBy) COLLATE utf8mb4_unicode_ci;
