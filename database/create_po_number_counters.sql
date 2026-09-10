-- Backing table for atomic PO-number generation. A bare `SELECT MAX(...)` (the
-- old approach in purchase_orders_repo._next_po_number) can't be locked with
-- FOR UPDATE since it has no row to lock - this gives it one real row per year
-- to lock immediately before use, same "lock, advance, use" shape as
-- check_vouchers_repo.create_voucher's payable row-locking.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_po_number_counters (
    year INT NOT NULL,
    lastSeq INT NOT NULL DEFAULT 0,
    PRIMARY KEY (year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed from whatever's already in tbl_purchase_orders so numbering continues
-- from where it left off, rather than restarting at 0001 for the current year.
INSERT INTO db_os_2026.tbl_po_number_counters (year, lastSeq)
SELECT
    CAST(SUBSTRING(poNumber, 1, 4) AS UNSIGNED) AS yr,
    MAX(CAST(SUBSTRING(poNumber, 6) AS UNSIGNED)) AS maxSeq
FROM db_os_2026.tbl_purchase_orders
WHERE poNumber REGEXP '^[0-9]{4}-[0-9]+$'
GROUP BY yr
ON DUPLICATE KEY UPDATE lastSeq = GREATEST(tbl_po_number_counters.lastSeq, VALUES(lastSeq));
