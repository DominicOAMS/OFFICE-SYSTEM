-- Migration: db_oams_app_2026.tbl_vehicle_info / tbl_fuelpo
--         -> db_os_2026.tbl_vehicles / tbl_fuel_pos (+ new tbl_fuel_po_approvers)
--
-- Follows the same shape as migrate_suppliers.sql: renames columns to
-- lowerCamelCase, re-types them, adds the audit-trail columns, and replaces
-- legacy free-text name/plate links with real foreign keys.
--
-- Notes on the source data (profiled before writing this):
--   * tbl_fuelpo is LIVE (newest row is from yesterday) and its FPONumber is a
--     clean, gapless-enough PK (1..1081, 1078 rows, no exact duplicates) that
--     staff already recognize as the PO number. It is preserved as the new
--     tbl_fuel_pos.id (explicit INSERT), and AUTO_INCREMENT is reset to 1082
--     afterward so new requests continue the same sequence instead of
--     restarting at 1.
--   * tbl_vehicle_info.Assignee and tbl_fuelpo.Driver are free-text names,
--     resolved to tbl_users.id by exact trimmed/case-insensitive match. The
--     literal string 'None' (9 Assignee rows) is treated as unassigned, not a
--     name. Names that don't match anything (Assignee: 'Chief' - ambiguous,
--     2 users hold that position; 'JM'; 'Giliw Ibanez'; 'Erika Sy'; 'Mary
--     Grace Lacson'; 'Maria Teresita Lagrada'. Driver: 'MARIA TERESITA
--     CACALDA'; 'HALAH ABDEL QADER'; one doubled-up name typo) are left NULL
--     with the raw text kept in legacyAssignee/legacyDriverName rather than
--     guessed at - the same call migrate_suppliers.sql made for spelling
--     variants it found.
--   * tbl_fuelpo has no separate "who submitted this" field - only Driver.
--     requestedByUserId is set equal to the resolved requestedForUserId as a
--     documented best-effort assumption for migrated history; the new Add
--     Fuel PO form will populate both independently going forward.
--   * PlateNumber -> vehicleId resolved against the newly-populated
--     tbl_vehicles.plateNumber. Only 1 of 1,078 rows (plate 'OA6 40A') has no
--     matching vehicle master row; it lands as NULL vehicleId with the plate
--     text kept in legacyPlateNumber.
--   * Odometer and Amount are VARCHAR in the legacy table and hold a lot of
--     free text alongside real numbers ('NA', 'FULL TANK', 'Please see
--     attached photo', '146233 km', '2k', 'TEST', ...). Cleaned the same way
--     migrate_suppliers.sql cleaned Price: strip commas/spaces, require the
--     remainder to fully match a plain-number pattern, else NULL. The 84
--     "FULL TANK"-style rows and other unparseable text are NOT discarded -
--     they're preserved verbatim in legacyOdometerText/legacyAmountText.
--     (The "please see attached photo" rows are the direct evidence behind
--     adding a real odometerAttachmentPath column - staff had nowhere to
--     actually attach the photo they were describing.)
--   * ApprovedBy is the literal string 'none' on all 1,078 rows and VerifiedBy
--     / ActualAmount / PurchaseDate / ExtRefNo are NULL or blank on all
--     1,078 rows - none of these are migrated, same call as dropping
--     ExtRefNo in migrate_suppliers.sql.
--   * Status collapses legacy's single-stage label into the new two-stage
--     workflow: 'For Approval' (10 rows, still genuinely open right now) ->
--     'Pending Approval' so they land as real actionable rows, not silently
--     closed history. 'Approved' and 'Printed' (already through whatever
--     approval existed historically) both -> 'Approved'. 'Rejected' ->
--     'Rejected'. Original value kept in legacyStatus.
--   * created_at/updated_at are VARCHAR but already well-formed
--     'YYYY-MM-DD HH:MM:SS' on every row (0 rows fail the format check), so a
--     plain CAST to DATETIME is enough - no cleaning needed.
--   * tbl_vehicle_info/tbl_fuelpo are utf8mb4_general_ci while the new tables
--     are utf8mb4_unicode_ci, so every cross-database string comparison below
--     is explicitly collated to avoid "illegal mix of collations" (no CONVERT
--     needed since both sides are already utf8mb4, only the collation
--     differs).

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_vehicles (
    id INT NOT NULL AUTO_INCREMENT,
    plateNumber VARCHAR(20) NOT NULL,
    vehicleModel VARCHAR(255) NULL,
    fuelType VARCHAR(50) NULL,
    assignedUserId INT NULL,
    legacyAssignee VARCHAR(255) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_vehicles_plateNumber (plateNumber),
    KEY idx_tbl_vehicles_assignedUserId (assignedUserId),
    KEY idx_tbl_vehicles_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_vehicles_assignedUser
        FOREIGN KEY (assignedUserId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_fuel_pos (
    id INT NOT NULL AUTO_INCREMENT,
    requestDate DATE NOT NULL,
    requestedForUserId INT NULL,
    legacyDriverName VARCHAR(255) NULL,
    requestedByUserId INT NULL,
    vehicleId INT NULL,
    legacyPlateNumber VARCHAR(20) NULL,
    fuelType VARCHAR(50) NULL,
    destination VARCHAR(255) NULL,
    purpose VARCHAR(255) NULL,
    odometer INT UNSIGNED NULL,
    odometerAttachmentPath VARCHAR(255) NULL,
    legacyOdometerText VARCHAR(255) NULL,
    amountRequested DECIMAL(12,2) NULL,
    legacyAmountText VARCHAR(255) NULL,
    approverUserId INT NULL,
    approverActionAt DATETIME NULL,
    approverRemarks VARCHAR(255) NULL,
    finalApproverUserId INT NULL,
    finalApproverActionAt DATETIME NULL,
    finalApproverRemarks VARCHAR(255) NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Pending Approval',
    legacyStatus VARCHAR(30) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_fuel_pos_requestedForUserId (requestedForUserId),
    KEY idx_tbl_fuel_pos_requestedByUserId (requestedByUserId),
    KEY idx_tbl_fuel_pos_vehicleId (vehicleId),
    KEY idx_tbl_fuel_pos_approverUserId (approverUserId),
    KEY idx_tbl_fuel_pos_finalApproverUserId (finalApproverUserId),
    KEY idx_tbl_fuel_pos_status (status),
    KEY idx_tbl_fuel_pos_isDeleted (isDeleted),
    CONSTRAINT fk_tbl_fuel_pos_requestedForUser
        FOREIGN KEY (requestedForUserId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_fuel_pos_requestedByUser
        FOREIGN KEY (requestedByUserId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_fuel_pos_vehicle
        FOREIGN KEY (vehicleId) REFERENCES db_os_2026.tbl_vehicles (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_fuel_pos_approverUser
        FOREIGN KEY (approverUserId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_fuel_pos_finalApproverUser
        FOREIGN KEY (finalApproverUserId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- No legacy data to seed this from - admins populate it from the new
-- Parameters > Fuel Approvers page. userId+role is unique (not
-- userId+role+isDeleted): "removing" an approver soft-deletes their one row,
-- and re-adding them later reuses/undeletes that same row, so there is never
-- more than one row per (userId, role) at all.
CREATE TABLE IF NOT EXISTS db_os_2026.tbl_fuel_po_approvers (
    id INT NOT NULL AUTO_INCREMENT,
    userId INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_fuel_po_approvers_user_role (userId, role),
    KEY idx_tbl_fuel_po_approvers_role (role),
    CONSTRAINT fk_tbl_fuel_po_approvers_user
        FOREIGN KEY (userId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) Vehicle fleet master.
INSERT INTO db_os_2026.tbl_vehicles
    (plateNumber, vehicleModel, fuelType, assignedUserId, legacyAssignee, status, isDeleted, createdAt, updatedAt)
SELECT
    TRIM(v.PlateNumber),
    NULLIF(TRIM(v.VehicleModel), ''),
    NULLIF(NULLIF(TRIM(v.FuelType), ''), '-'),
    u.id,
    CASE
        WHEN u.id IS NULL AND UPPER(TRIM(COALESCE(v.Assignee, ''))) NOT IN ('', 'NONE')
            THEN TRIM(v.Assignee)
        ELSE NULL
    END,
    'Active',
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_vehicle_info v
LEFT JOIN db_os_2026.tbl_users u
    ON u.name = TRIM(v.Assignee) COLLATE utf8mb4_unicode_ci
   AND u.isDeleted = 0
   AND UPPER(TRIM(COALESCE(v.Assignee, ''))) NOT IN ('', 'NONE');

-- 2) Fuel PO requests, linked through the new integer ids. id is explicitly
--    set to the legacy FPONumber to preserve the sequence (see header note).
INSERT INTO db_os_2026.tbl_fuel_pos
    (id, requestDate, requestedForUserId, legacyDriverName, requestedByUserId,
     vehicleId, legacyPlateNumber, fuelType, destination, purpose,
     odometer, legacyOdometerText, amountRequested, legacyAmountText,
     status, legacyStatus, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    f.FPONumber,
    COALESCE(f.RequestDate, CAST(f.created_at AS DATE)),
    du.id,
    CASE WHEN du.id IS NULL AND TRIM(COALESCE(f.Driver, '')) <> '' THEN TRIM(f.Driver) ELSE NULL END,
    du.id,
    veh.id,
    CASE WHEN veh.id IS NULL AND TRIM(COALESCE(f.PlateNumber, '')) <> '' THEN TRIM(f.PlateNumber) ELSE NULL END,
    NULLIF(TRIM(f.FuelType), ''),
    NULLIF(TRIM(f.Destination), ''),
    NULLIF(TRIM(f.Purpose), ''),
    CASE
        WHEN TRIM(REPLACE(REPLACE(COALESCE(f.Odometer, ''), ',', ''), ' ', '')) REGEXP '^[0-9]+$'
        THEN CAST(TRIM(REPLACE(REPLACE(f.Odometer, ',', ''), ' ', '')) AS UNSIGNED)
        ELSE NULL
    END,
    CASE
        WHEN TRIM(REPLACE(REPLACE(COALESCE(f.Odometer, ''), ',', ''), ' ', '')) REGEXP '^[0-9]+$'
        THEN NULL
        ELSE NULLIF(TRIM(f.Odometer), '')
    END,
    CASE
        WHEN TRIM(REPLACE(REPLACE(COALESCE(f.Amount, ''), ',', ''), ' ', '')) REGEXP '^[0-9]+(\\.[0-9]+)?$'
        THEN CAST(TRIM(REPLACE(REPLACE(f.Amount, ',', ''), ' ', '')) AS DECIMAL(12,2))
        ELSE NULL
    END,
    CASE
        WHEN TRIM(REPLACE(REPLACE(COALESCE(f.Amount, ''), ',', ''), ' ', '')) REGEXP '^[0-9]+(\\.[0-9]+)?$'
        THEN NULL
        ELSE NULLIF(TRIM(f.Amount), '')
    END,
    CASE UPPER(TRIM(COALESCE(f.Status, '')))
        WHEN 'FOR APPROVAL' THEN 'Pending Approval'
        WHEN 'APPROVED' THEN 'Approved'
        WHEN 'PRINTED' THEN 'Approved'
        WHEN 'REJECTED' THEN 'Rejected'
        ELSE 'Pending Approval'
    END,
    NULLIF(TRIM(f.Status), ''),
    0, NULL, CAST(f.created_at AS DATETIME), NULL, CAST(f.updated_at AS DATETIME)
FROM db_oams_app_2026.tbl_fuelpo f
LEFT JOIN db_os_2026.tbl_users du
    ON du.name = TRIM(f.Driver) COLLATE utf8mb4_unicode_ci
   AND du.isDeleted = 0
   AND TRIM(COALESCE(f.Driver, '')) <> ''
LEFT JOIN db_os_2026.tbl_vehicles veh
    ON veh.plateNumber = TRIM(f.PlateNumber) COLLATE utf8mb4_unicode_ci;

-- 3) Continue the PO-number sequence from where the legacy system left off
--    (max FPONumber is 1081) instead of colliding with/restarting it.
ALTER TABLE db_os_2026.tbl_fuel_pos AUTO_INCREMENT = 1082;
