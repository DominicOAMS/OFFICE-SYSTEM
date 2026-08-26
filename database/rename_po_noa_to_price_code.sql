-- Renames tbl_purchase_orders.noaNumber -> priceCode.
--
-- Legacy's own live Create PO screen already labels this field "Price Code"
-- on screen (purchase_order.blade.php) even though the underlying column
-- stayed named NOANumber from an older naming convention. It holds a value
-- from a supplier's tbl_suppliers_products.priceCode, used to scope which of
-- that supplier's products can go on the PO. Renaming the column to match
-- what it actually is, per this project's established naming convention.
--
-- CHANGE COLUMN (not DROP+ADD) preserves the 107 existing non-blank values
-- out of 1,773 migrated rows.

ALTER TABLE tbl_purchase_orders
    CHANGE COLUMN noaNumber priceCode VARCHAR(255) NULL;
