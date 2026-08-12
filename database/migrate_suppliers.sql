-- Migration: db_oams_app_2026.tbl_supplier / tbl_supplier_products
--         -> db_os_2026.tbl_suppliers / tbl_suppliers_products
--
-- Follows the same shape as migrate_customers.sql: renames columns to
-- lowerCamelCase, re-types them, adds the audit-trail columns, and replaces the
-- legacy free-text SupplierID link with a real supplierId -> tbl_suppliers(id)
-- foreign key.
--
-- Notes on the source data (profiled before writing this):
--   * SupplierID is a business code, not a number ('0016A', '0016BATMC', …),
--     max length 16. Kept as `code` with a unique index; the new integer `id`
--     is what tbl_suppliers_products points at.
--   * Status is 'AC'/'IN' (94/15) -> expanded to 'Active'/'Inactive'. This is a
--     business status and is deliberately separate from the isDeleted flag.
--   * TNumber/FNumber renamed to telephoneNumber/faxNumber.
--   * Price is a VARCHAR holding values like ' 4,645.20 ' with comma thousands
--     separators, ordinary spaces and non-breaking spaces (U+00A0). Cleaned to
--     DECIMAL(12,2) here. 5 legitimately negative prices are preserved. 9 rows
--     cannot be parsed at all (8 empty strings and one literal 'O' typo) and
--     land as NULL. No source row has more than 2 decimal places, so nothing is
--     rounded away.
--   * 2 product rows reference supplier codes with no tbl_supplier row (RO53,
--     RO54). They are backfilled as placeholder suppliers below so the foreign
--     key can be added without dropping data.
--   * 303 (supplierId, catalog) combinations repeat: these are price history
--     rows distinguished by effectiveDate, so there is deliberately NO unique
--     constraint on that pair.
--   * ExtRefNo was dropped: it is blank on all 3,280 legacy rows, so there is
--     nothing to carry over (same call migrate_customers.sql made for its own
--     ExtRefNo column).
--   * Catalog/Description/Unit/PriceCode contain stray tab and newline
--     characters in the legacy data (e.g. a unit stored as "\tBOX"), so those
--     are stripped on the way in. Genuine spelling variants that exist in the
--     source ("BOTTLE" vs "BOTTE", "BOX" vs "BXS") are left untouched — that is
--     a data-cleanup decision for the business, not something to guess at here.
--   * tbl_supplier_products carries real CreatedBy/ModifiedBy names
--     ('Fredric Goza', 'John Bryan Arcega', 'Dominic Manjares'). Those are
--     resolved to tbl_users.id so the audit trail survives the migration;
--     unmatched names fall back to NULL.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_suppliers (
    id INT NOT NULL AUTO_INCREMENT,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(30) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    address VARCHAR(255) NULL,
    telephoneNumber VARCHAR(100) NULL,
    faxNumber VARCHAR(100) NULL,
    email VARCHAR(255) NULL,
    paymentTerm VARCHAR(100) NULL,
    tin VARCHAR(30) NULL,
    priceType VARCHAR(30) NOT NULL DEFAULT 'Regular',
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tbl_suppliers_code (code),
    KEY idx_tbl_suppliers_name (name),
    KEY idx_tbl_suppliers_isDeleted (isDeleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_suppliers_products (
    id INT NOT NULL AUTO_INCREMENT,
    supplierId INT NOT NULL,
    catalog VARCHAR(50) NULL,
    description TEXT NULL,
    category VARCHAR(50) NULL,
    unit VARCHAR(20) NULL,
    price DECIMAL(12,2) NULL,
    priceCode VARCHAR(30) NULL,
    effectiveDate DATE NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_suppliers_products_supplierId (supplierId),
    KEY idx_tbl_suppliers_products_catalog (catalog),
    CONSTRAINT fk_tbl_suppliers_products_supplier
        FOREIGN KEY (supplierId) REFERENCES db_os_2026.tbl_suppliers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1) Real suppliers.
INSERT INTO db_os_2026.tbl_suppliers
    (code, name, category, status, address, telephoneNumber, faxNumber, email,
     paymentTerm, tin, priceType, isDeleted, createdAt, updatedAt)
SELECT
    TRIM(s.SupplierID),
    NULLIF(TRIM(s.Name), ''),
    NULLIF(TRIM(s.Category), ''),
    CASE UPPER(TRIM(COALESCE(s.Status, '')))
        WHEN 'AC' THEN 'Active'
        WHEN 'IN' THEN 'Inactive'
        ELSE 'Active'
    END,
    NULLIF(TRIM(s.Address), ''),
    NULLIF(TRIM(s.TNumber), ''),
    NULLIF(TRIM(s.FNumber), ''),
    NULLIF(TRIM(s.Email), ''),
    NULLIF(TRIM(s.PaymentTerm), ''),
    NULLIF(TRIM(s.TIN), ''),
    COALESCE(NULLIF(TRIM(s.PriceType), ''), 'Regular'),
    0, NOW(), NOW()
FROM db_oams_app_2026.tbl_supplier s;

-- 2) Placeholder suppliers for codes used by tbl_supplier_products that have no
--    tbl_supplier row, so step 3 cannot orphan (or silently drop) any rows.
INSERT INTO db_os_2026.tbl_suppliers
    (code, name, status, isDeleted, createdAt, updatedAt)
SELECT DISTINCT
    TRIM(p.SupplierID),
    CONCAT('[Unlinked] ', TRIM(p.SupplierID)),
    'Inactive',
    0, NOW(), NOW()
-- tbl_supplier is latin1 and tbl_supplier_products is utf8mb4, so the legacy
-- side is converted before being collated for comparison.
FROM db_oams_app_2026.tbl_supplier_products p
LEFT JOIN db_oams_app_2026.tbl_supplier s
    ON CONVERT(TRIM(s.SupplierID) USING utf8mb4) COLLATE utf8mb4_unicode_ci
       = TRIM(p.SupplierID) COLLATE utf8mb4_unicode_ci
WHERE s.SupplierID IS NULL;

-- 3) Supplier product / price list, linked through the new integer id.
-- category has no legacy counterpart on tbl_supplier_products, so it is
-- backfilled from the inventory master where the catalog matches (and left NULL
-- otherwise). It exists for parity with tbl_customers_products and is filled in
-- going forward by the Add/Edit price form.
INSERT INTO db_os_2026.tbl_suppliers_products
    (supplierId, catalog, description, category, unit, price, priceCode, effectiveDate,
     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    sup.id,
    NULLIF(TRIM(REPLACE(REPLACE(REPLACE(p.Catalog, CHAR(9), ''), CHAR(10), ''), CHAR(13), '')), ''),
    NULLIF(TRIM(REPLACE(REPLACE(REPLACE(p.Description, CHAR(9), ' '), CHAR(10), ' '), CHAR(13), ' ')), ''),
    inv.category,
    NULLIF(TRIM(REPLACE(REPLACE(REPLACE(p.Unit, CHAR(9), ''), CHAR(10), ''), CHAR(13), '')), ''),
    CASE
        WHEN TRIM(REPLACE(REPLACE(REPLACE(p.Price, ',', ''), UNHEX('C2A0'), ''), ' ', ''))
             REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
        THEN CAST(TRIM(REPLACE(REPLACE(REPLACE(p.Price, ',', ''), UNHEX('C2A0'), ''), ' ', '')) AS DECIMAL(12,2))
        ELSE NULL
    END,
    NULLIF(TRIM(REPLACE(REPLACE(REPLACE(p.PriceCode, CHAR(9), ''), CHAR(10), ''), CHAR(13), '')), ''),
    p.EffectiveDate,
    0,
    cu.id,
    COALESCE(p.CreatedDate, NOW()),
    mu.id,
    COALESCE(p.ModifiedDate, p.CreatedDate, NOW())
-- The legacy tables are utf8mb4_general_ci / latin1 while the new ones are
-- utf8mb4_unicode_ci, so every cross-database string comparison below is
-- explicitly collated to avoid "illegal mix of collations".
FROM db_oams_app_2026.tbl_supplier_products p
JOIN db_os_2026.tbl_suppliers sup
    ON sup.code = TRIM(p.SupplierID) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_users cu
    ON cu.name = TRIM(p.CreatedBy) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_users mu
    ON mu.name = TRIM(p.ModifiedBy) COLLATE utf8mb4_unicode_ci
LEFT JOIN db_os_2026.tbl_inventory_items inv
    ON inv.catalog = TRIM(p.Catalog) COLLATE utf8mb4_unicode_ci
   AND inv.isDeleted = 0;
