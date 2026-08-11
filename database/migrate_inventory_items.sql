-- Migration: db_oams_app_2026.tbl_INInventoryItem -> db_os_2026.tbl_inventory_items
--
-- This is the master catalog (currently VITROS-only; supplier-sourced "Other
-- Products" items still live in the legacy tbl_supplier_products, which will
-- be migrated with the Suppliers module). Brought in now as a read-only
-- lookup so the Customers > Product Price List "Add Product" screen can
-- autocomplete by catalog number or product name and auto-fill description
-- and unit, matching the legacy /customer_details flow.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_inventory_items (
    id INT NOT NULL AUTO_INCREMENT,
    catalog VARCHAR(20) NOT NULL,
    description VARCHAR(255) NULL,
    status VARCHAR(5) NULL,
    category VARCHAR(50) NULL,
    groupType VARCHAR(50) NULL,
    baseUnit VARCHAR(30) NULL,
    salesUnit VARCHAR(30) NULL,
    purchaseUnit VARCHAR(30) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_inventory_items_catalog (catalog)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_inventory_items
    (catalog, description, status, category, groupType, baseUnit, salesUnit, purchaseUnit, isDeleted, createdAt, updatedAt)
SELECT
    Catalog,
    NULLIF(TRIM(Description), ''),
    NULLIF(TRIM(Status), ''),
    NULLIF(TRIM(Category), ''),
    NULLIF(TRIM(GroupType), ''),
    NULLIF(TRIM(BaseUnit), ''),
    NULLIF(TRIM(SalesUnit), ''),
    NULLIF(TRIM(PurchaseUnit), ''),
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_INInventoryItem;
