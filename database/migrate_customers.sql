-- Migration: db_oams_app_2026.tbl_customerinfo / tbl_customer_products
--         -> db_os_2026.tbl_customers / tbl_customers_products
--
-- Renames + re-types the legacy schema, adds audit trail columns, and adds a
-- real customerId -> tbl_customers(id) foreign key (the legacy tables only
-- related customers to products by a free-text CustomerID string, with 4
-- codes used by tbl_customer_products that have no tbl_customerinfo row at
-- all: PBI-2017-45v1, PBI-2023-74, PLL-2025-115, PUL-2022-1 — 99 rows total.
-- Those are backfilled as placeholder customers below so no product rows
-- are lost. The legacy Price column is a VARCHAR with comma thousands
-- separators and some literal "-"/"" placeholders — cleaned to DECIMAL here.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_customers (
    id INT NOT NULL AUTO_INCREMENT,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    address VARCHAR(255) NULL,
    tin VARCHAR(30) NULL,
    paymentTermDays INT NOT NULL DEFAULT 0,
    salesRep VARCHAR(100) NULL,
    customerType VARCHAR(30) NULL,
    vpSupplierId VARCHAR(45) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_customers_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_customers_products (
    id INT NOT NULL AUTO_INCREMENT,
    customerId INT NOT NULL,
    priceCode VARCHAR(30) NULL,
    catalog VARCHAR(50) NULL,
    customerDescription VARCHAR(150) NULL,
    category VARCHAR(50) NULL,
    unit VARCHAR(20) NULL,
    price DECIMAL(12,2) NULL,
    effectiveDate DATE NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_customers_products_customerId (customerId),
    CONSTRAINT fk_tbl_customers_products_customer
        FOREIGN KEY (customerId) REFERENCES db_os_2026.tbl_customers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) Real customers.
INSERT INTO db_os_2026.tbl_customers
    (code, name, address, tin, paymentTermDays, salesRep, customerType, vpSupplierId, isDeleted, createdAt, updatedAt)
SELECT
    ci.customerID,
    NULLIF(TRIM(ci.Name), ''),
    NULLIF(TRIM(ci.Address), ''),
    NULLIF(TRIM(ci.TIN), ''),
    COALESCE(ci.PaymentTermDays, 0),
    NULLIF(TRIM(ci.SalesRep), ''),
    NULLIF(TRIM(ci.CustomerType), ''),
    NULLIF(TRIM(ci.VPSupplierID), ''),
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_customerinfo ci;

-- 2) Placeholder customers for codes referenced by tbl_customer_products but
--    missing from tbl_customerinfo, so the FK below can't orphan any rows.
INSERT INTO db_os_2026.tbl_customers
    (code, name, isDeleted, createdAt, updatedAt)
SELECT DISTINCT
    cp.CustomerID,
    COALESCE(NULLIF(TRIM(cp.CustomerName), ''), cp.CustomerID),
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_customer_products cp
LEFT JOIN db_oams_app_2026.tbl_customerinfo ci ON ci.customerID = cp.CustomerID
WHERE ci.customerID IS NULL;

-- 3) Customer-specific product/price list, linked via the new integer id.
--    (ExtRefNo was dropped — checked against the source data and it's blank
--    on all 8,286 legacy rows, so there was nothing to carry over.)
INSERT INTO db_os_2026.tbl_customers_products
    (customerId, priceCode, catalog, customerDescription, category, unit, price, effectiveDate, isDeleted, createdAt, updatedAt)
SELECT
    c.id,
    NULLIF(TRIM(cp.PriceCode), ''),
    NULLIF(TRIM(cp.Catalog), ''),
    NULLIF(TRIM(cp.CustomerDescription), ''),
    NULLIF(TRIM(cp.Category), ''),
    NULLIF(TRIM(cp.Unit), ''),
    CASE WHEN TRIM(REPLACE(cp.Price, ',', '')) IN ('', '-') THEN NULL
         ELSE CAST(REPLACE(cp.Price, ',', '') AS DECIMAL(12,2))
    END,
    cp.EffectiveDate,
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_customer_products cp
JOIN db_os_2026.tbl_customers c ON c.code = cp.CustomerID;
