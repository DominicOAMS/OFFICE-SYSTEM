from .db import get_connection

_DR_COLUMNS = """
    r.*,
    cust.code AS liveCustomerCode,
    creator.name AS createdByName,
    voider.name AS voidedByName,
    wt.status AS transactionStatus
"""

_DR_FROM = """
    FROM tbl_delivery_receipts r
    LEFT JOIN tbl_customers cust ON cust.id = r.customerId
    LEFT JOIN tbl_users creator ON creator.id = r.createdBy
    LEFT JOIN tbl_users voider ON voider.id = r.voidedBy
    LEFT JOIN tbl_warehouse_transactions wt ON wt.id = r.transactionId
"""


def _filter_clauses(search, status):
    sql = " WHERE r.isDeleted = 0"
    params = []
    if status:
        sql += " AND r.status = %s"
        params.append(status)
    if search:
        sql += """ AND (
            r.drNumber LIKE %s OR r.deliveredTo LIKE %s OR r.customerPo LIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_delivery_receipt_items i
                WHERE i.deliveryReceiptId = r.id AND i.description LIKE %s
            )
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like]
    return sql, params


def count_delivery_receipts(search=None, status=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n" + _DR_FROM
            extra_sql, params = _filter_clauses(search, status)
            cur.execute(sql + extra_sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_delivery_receipts(search=None, status=None, limit=None, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT " + _DR_COLUMNS + _DR_FROM
            extra_sql, params = _filter_clauses(search, status)
            sql += extra_sql + " ORDER BY r.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params = params + [int(limit), int(offset)]
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_delivery_receipt(dr_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _DR_COLUMNS + _DR_FROM + " WHERE r.id = %s LIMIT 1",
                (dr_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def list_items_for_delivery_receipts(dr_ids):
    """Every line item for a page of delivery receipts, keyed by deliveryReceiptId - mirrors
    invoices_repo.list_items_for_invoices."""
    if not dr_ids:
        return {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(dr_ids))
            cur.execute(
                f"""
                SELECT * FROM tbl_delivery_receipt_items
                WHERE deliveryReceiptId IN ({placeholders})
                ORDER BY deliveryReceiptId, sequence
                """,
                dr_ids,
            )
            result = {}
            for row in cur.fetchall():
                result.setdefault(row["deliveryReceiptId"], []).append(row)
            return result
    finally:
        conn.close()


def _next_dr_number(cur):
    """Legacy DR numbers are a flat, tightly-sequential integer series with no per-year
    prefix (unlike PO/voucher numbers) - just MAX+1 across the whole table."""
    cur.execute("SELECT MAX(CAST(drNumber AS UNSIGNED)) AS maxNum FROM tbl_delivery_receipts")
    next_num = (cur.fetchone()["maxNum"] or 0) + 1
    return str(next_num)


def create_delivery_receipt(data, created_by):
    """Resolves a best-effort transactionId cross-reference at creation time only (matching
    a Warehouse Transaction that already has this same drNumber typed into it) - not
    re-resolved later if one shows up afterward. Items are inserted after the header the
    same way every other multi-row create does; no money total here, but the header/items
    split still benefits from one connection/transaction so a partial failure can't leave an
    orphaned header."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            dr_number = _next_dr_number(cur)
            cur.execute(
                """
                SELECT id FROM tbl_warehouse_transactions
                WHERE drNumber = %s AND isDeleted = 0
                LIMIT 1
                """,
                (dr_number,),
            )
            wt_row = cur.fetchone()
            transaction_id = wt_row["id"] if wt_row else None

            cur.execute(
                """
                INSERT INTO tbl_delivery_receipts
                    (drNumber, customerId, customerCode, deliveredTo, tin, address,
                     deliveryDate, customerPo, terms, branch, notes, transactionId,
                     status, createdBy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Created', %s)
                """,
                (
                    dr_number, data["customerId"], data["customerCode"], data["deliveredTo"],
                    data["tin"], data["address"], data["deliveryDate"], data["customerPo"],
                    data["terms"], data["branch"], data["notes"], transaction_id, created_by,
                ),
            )
            dr_id = cur.lastrowid
            for seq, item in enumerate(data["items"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_delivery_receipt_items
                        (deliveryReceiptId, sequence, itemId, catalogCode, description,
                         unit, category, quantity, lot, expiryDate, customerPo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        dr_id, seq, item["itemId"], item["catalogCode"], item["description"],
                        item["unit"], item["category"], item["quantity"], item["lot"],
                        item["expiryDate"], item["customerPo"],
                    ),
                )
        conn.commit()
        return dr_id, dr_number
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_printed(dr_id, printed_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_delivery_receipts
                SET status = 'Printed', updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (printed_by, dr_id),
            )
    finally:
        conn.close()


def mark_finished(dr_id, finished_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_delivery_receipts
                SET status = 'Finished', updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (finished_by, dr_id),
            )
    finally:
        conn.close()


def void(dr_id, voided_by, reason):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_delivery_receipts
                SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (voided_by, reason, voided_by, dr_id),
            )
    finally:
        conn.close()
