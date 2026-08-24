from datetime import date

from .db import get_connection

_PO_COLUMNS = """
    po.*,
    creator.name AS createdByName,
    appr.name AS approverName
"""

_PO_FROM = """
    FROM tbl_purchase_orders po
    LEFT JOIN tbl_users creator ON creator.id = po.createdBy
    LEFT JOIN tbl_users appr ON appr.id = po.approverUserId
"""


def _filter_clauses(search, status):
    sql = " WHERE po.isDeleted = 0"
    params = []
    if status:
        sql += " AND po.status = %s"
        params.append(status)
    if search:
        # po.supplierName/branch cover the header; the EXISTS covers a line item's
        # description, which has no rollup column on the header to search instead.
        sql += """ AND (
            po.poNumber LIKE %s OR po.supplierName LIKE %s OR po.branch LIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_purchase_order_items i
                WHERE i.purchaseOrderId = po.id AND i.description LIKE %s
            )
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like]
    return sql, params


def count_purchase_orders(search=None, status=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n" + _PO_FROM
            extra_sql, params = _filter_clauses(search, status)
            cur.execute(sql + extra_sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_purchase_orders(search=None, status=None, limit=None, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT " + _PO_COLUMNS + _PO_FROM
            extra_sql, params = _filter_clauses(search, status)
            sql += extra_sql + " ORDER BY po.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params = params + [int(limit), int(offset)]
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_purchase_order(po_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _PO_COLUMNS + _PO_FROM + " WHERE po.id = %s LIMIT 1",
                (po_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def list_active_inventory_items():
    """Same catalog customers_repo.list_active_inventory_items() reads, but this one
    also selects id - Purchase Order line items store itemId as a real FK, which the
    customer-products picker never needed."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, catalog, description, category, groupType, baseUnit, salesUnit, purchaseUnit
                FROM tbl_inventory_items
                WHERE isDeleted = 0 AND status = 'AC'
                ORDER BY catalog ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def _next_po_number(cur, year):
    """Continues the legacy 'YYYY-NNNN' scheme, scoped per year. Computed inside the
    caller's transaction (same connection, right before the INSERT) rather than as a
    separate autocommit query, to keep the read-then-insert window as short as possible -
    this app has no other place that generates a shared sequential business number, so
    there's no existing helper to reuse."""
    prefix = f"{year}-"
    cur.execute(
        """
        SELECT MAX(CAST(SUBSTRING(poNumber, 6) AS UNSIGNED)) AS maxSeq
        FROM tbl_purchase_orders
        WHERE poNumber LIKE %s
        """,
        (prefix + "%",),
    )
    next_seq = (cur.fetchone()["maxSeq"] or 0) + 1
    return f"{prefix}{next_seq:04d}"


def create_purchase_order(data, created_by):
    """Insert the PO header and its line items in one transaction.

    Same reasoning as create_fuel_po (the other explicit transaction in this codebase):
    the header's vatableAmount/vatAmount/totalAmount are computed from data["items"]
    BEFORE those items exist as rows, so a partial failure under autocommit would leave
    a PO whose stored total doesn't match its (unsaved) items - exactly the kind of drift
    the legacy data migration found and flagged as a problem to avoid going forward.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            po_number = _next_po_number(cur, date.today().year)
            cur.execute(
                """
                INSERT INTO tbl_purchase_orders
                    (poNumber, orderDate, supplierId, supplierName, supplierAddress,
                     supplierTelephone, supplierFax, supplierEmail,
                     deliveryAddress, deliveryTelephone, deliveryMobileNumber,
                     deliveryTerm, paymentTerm, deliveryDate, paymentDueDate,
                     vatableAmount, vatAmount, totalAmount, status, noaNumber, notes,
                     attachmentPath, branch, approverUserId,
                     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, CURDATE(), %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s, %s,
                     %s, %s, %s, 'Pending Approval', %s, %s,
                     %s, %s, %s,
                     0, %s, NOW(), %s, NOW())
                """,
                (
                    po_number,
                    data["supplierId"],
                    data["supplierName"],
                    data["supplierAddress"],
                    data["supplierTelephone"],
                    data["supplierFax"],
                    data["supplierEmail"],
                    data["deliveryAddress"],
                    data["deliveryTelephone"],
                    data["deliveryMobileNumber"],
                    data["deliveryTerm"],
                    data["paymentTerm"],
                    data["deliveryDate"],
                    data["paymentDueDate"],
                    data["vatableAmount"],
                    data["vatAmount"],
                    data["totalAmount"],
                    data["noaNumber"],
                    data["notes"],
                    data["attachmentPath"],
                    data["branch"],
                    data["approverUserId"],
                    created_by,
                    created_by,
                ),
            )
            purchase_order_id = cur.lastrowid

            for seq, item in enumerate(data["items"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_purchase_order_items
                        (purchaseOrderId, sequence, itemId, catalogCode, description, unit,
                         quantity, quantityServed, unitCost, amount, allocation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
                    """,
                    (
                        purchase_order_id,
                        seq,
                        item["itemId"],
                        item["catalogCode"],
                        item["description"],
                        item["unit"],
                        item["quantity"],
                        item["unitCost"],
                        item["amount"],
                        item["allocation"],
                    ),
                )

        conn.commit()
        return purchase_order_id, po_number
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_items_for_purchase_orders(po_ids):
    """Every line item for a page of POs, keyed by purchaseOrderId. Always exactly one
    query no matter how many POs are on the page - same shape as
    fuel_po_repo.list_trips_for_fuel_pos, just one level instead of two."""
    po_ids = [int(i) for i in po_ids]  # coerce BEFORE interpolating placeholders
    if not po_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(po_ids))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM tbl_purchase_order_items
                WHERE purchaseOrderId IN ({placeholders})
                ORDER BY purchaseOrderId ASC, sequence ASC
                """,
                po_ids,
            )
            items = cur.fetchall()
    finally:
        conn.close()

    items_by_po = {}
    for item in items:
        items_by_po.setdefault(item["purchaseOrderId"], []).append(item)
    return items_by_po


def get_items_for_purchase_order(po_id):
    """One PO's items - thin wrapper so single-record callers don't build a list."""
    return list_items_for_purchase_orders([po_id]).get(int(po_id), [])


def soft_delete_purchase_order(po_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_purchase_orders SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, po_id),
            )
    finally:
        conn.close()


def approve(po_id, approved_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_purchase_orders
                SET status = 'Approved', approverActionAt = NOW(), approverRemarks = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (remarks, approved_by, po_id),
            )
    finally:
        conn.close()


def reject(po_id, rejected_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_purchase_orders
                SET status = 'Rejected', approverActionAt = NOW(), approverRemarks = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (remarks, rejected_by, po_id),
            )
    finally:
        conn.close()
