-- New table: db_os_2026.tbl_purchase_order_approvers
--
-- Single-role version of tbl_fuel_po_approvers - Purchase Orders have one
-- approval stage (not Fuel PO's Approver + Final Approver), so there is no
-- `role` column at all: the unique key is just userId. No legacy data to
-- seed; admins populate this from the new Parameters > PO Approvers page,
-- the same way Fuel Approvers started empty.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_purchase_order_approvers (
    id INT NOT NULL AUTO_INCREMENT,
    userId INT NOT NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_purchase_order_approvers_user (userId),
    CONSTRAINT fk_tbl_purchase_order_approvers_user
        FOREIGN KEY (userId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
