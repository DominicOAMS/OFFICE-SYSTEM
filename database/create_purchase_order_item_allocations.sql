-- New table: tbl_purchase_order_item_allocations
--
-- Records which customer(s) a PO line item's stock is earmarked for, and how
-- much of the ordered quantity goes to each - e.g. 50 boxes ordered, 20 to
-- Customer A, 20 to Customer B, 10 to Customer C, so a PO can be traced back
-- to the customer(s) it was served for.
--
-- This is a real, established ERP pattern (NetSuite's "Order Allocation",
-- Dynamics' sales-order allocation/fulfillment) - one line item can have
-- several allocation rows; sum(quantity) should not exceed the line's own
-- quantity (enforced in the app, same as other business rules in this repo).
--
-- Legacy already tracked this, just as unstructured free text on
-- tbl_purchase_order_items.allocation (e.g. "PUL-2018-17:PAMANA MEDICAL
-- CENTER->1"). That column is left in place (it's real historical data,
-- useful as a raw-text fallback) but the app no longer writes to it -
-- migrate_legacy_allocations.py parses it into this table instead.
--
-- No isDeleted/createdBy/updatedBy: matches tbl_purchase_order_items' own
-- lighter audit shape - both are per-PO child rows created once alongside
-- their PO and never independently edited or deleted after the fact.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_purchase_order_item_allocations (
    id INT NOT NULL AUTO_INCREMENT,
    purchaseOrderItemId INT NOT NULL,
    customerId INT NOT NULL,
    quantity DECIMAL(12,2) NOT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_po_item_allocations_item (purchaseOrderItemId),
    KEY idx_tbl_po_item_allocations_customer (customerId),
    CONSTRAINT fk_tbl_po_item_allocations_item
        FOREIGN KEY (purchaseOrderItemId) REFERENCES db_os_2026.tbl_purchase_order_items (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tbl_po_item_allocations_customer
        FOREIGN KEY (customerId) REFERENCES db_os_2026.tbl_customers (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
