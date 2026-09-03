-- Migration: db_oams_app_2026.tbl_inventory_gatepass -> db_os_2026.tbl_gatepasses
--
-- The warehouse exit log - which driver left, cold-chain temperature, which invoices/DRs
-- went out. A straightforward column-for-column copy: this table has no customer/supplier/
-- item reference to resolve at all, just free text.
--
-- Notes on the source data (profiled before writing this):
--   * id is a fresh surrogate - the legacy id is a pure internal counter never referenced
--     by any other table, no reason to preserve it (unlike drNumber/invoiceNumber, which are
--     real business-facing document numbers).
--   * Invoices is kept as free text (invoicesText here), deliberately NOT parsed into
--     structured invoice links. Unlike Collections' clean comma-separated Invoices field
--     (93% match once normalized), this one mixes abbreviated numbers, embedded DR
--     references, and inconsistent prefixes in the same field - e.g.
--     "SI.NO.212668,2644,2655,...", "DR.NO. 007694/ SI.NO. 212661,...". Reliably resolving
--     that would mean guessing, not migrating, so it stays free text - "drop, don't patch".
--   * Status is 100% 'Created' in the legacy data (607 of 607 rows) - the new workflow adds
--     a Void status that simply never gets used by any migrated row, same as any other
--     migration where the terminal-but-unused status doesn't appear in the source data yet.
--   * CheckedBy is 100% blank/unused in the legacy data - migrated as a column anyway
--     (kept for future real use, per the approved plan) since it costs nothing to carry the
--     0 populated values across, but nothing in the new workflow gates on it.
--   * created_at/updated_at are already real DATETIME columns on this table (unlike most
--     other legacy tables, which store them as VARCHAR) - straight copy, no CAST needed.
--   * tbl_inventory_gatepass (legacy) is already utf8mb4.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_gatepasses (
    id INT NOT NULL AUTO_INCREMENT,
    deliveryStaff VARCHAR(255) NULL,
    transDate DATE NULL,
    transTime TIME NULL,
    temperature VARCHAR(20) NULL,
    invoicesText TEXT NULL,
    submittedBy VARCHAR(100) NULL,
    checkedBy VARCHAR(100) NULL,
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
    KEY idx_tbl_gatepasses_status (status),
    KEY idx_tbl_gatepasses_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_gatepasses_voidedBy
        FOREIGN KEY (voidedBy) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_gatepasses
    (deliveryStaff, transDate, transTime, temperature, invoicesText, submittedBy,
     checkedBy, status, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    NULLIF(TRIM(g.DeliveryStaff), ''),
    g.transDate,
    g.transTime,
    NULLIF(TRIM(g.Temperature), ''),
    NULLIF(TRIM(g.Invoices), ''),
    NULLIF(TRIM(g.SubmittedBy), ''),
    NULLIF(TRIM(g.CheckedBy), ''),
    COALESCE(NULLIF(TRIM(g.Status), ''), 'Created'),
    0, NULL, g.created_at, NULL, g.updated_at
FROM db_oams_app_2026.tbl_inventory_gatepass g;
