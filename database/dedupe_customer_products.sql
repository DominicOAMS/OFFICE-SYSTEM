-- Soft-deletes exact-duplicate rows in tbl_customers_products, keeping the
-- lowest id in each group as canonical. These duplicates came from the
-- original tbl_customer_products migration (see migrate_customers.sql) —
-- 2,548 groups / 2,557 extra rows, all sharing an identical customerId,
-- catalog, priceCode, unit, category, price, and effectiveDate, and the
-- exact same createdAt (inserted in one batch), confirming they're
-- migration artifacts rather than distinct historical prices.
--
-- Soft delete only (isDeleted = 1) — no rows are hard-deleted, so this is
-- fully reversible by flipping isDeleted back for a given id if needed.

UPDATE tbl_customers_products t
JOIN (
    SELECT t1.id
    FROM tbl_customers_products t1
    JOIN tbl_customers_products t2
        ON t2.customerId = t1.customerId
       AND t2.catalog <=> t1.catalog
       AND t2.priceCode <=> t1.priceCode
       AND t2.unit <=> t1.unit
       AND t2.category <=> t1.category
       AND t2.price <=> t1.price
       AND t2.effectiveDate <=> t1.effectiveDate
       AND t2.isDeleted = 0
       AND t2.id < t1.id
    WHERE t1.isDeleted = 0
) dup ON dup.id = t.id
SET t.isDeleted = 1, t.updatedBy = 57, t.updatedAt = NOW();
