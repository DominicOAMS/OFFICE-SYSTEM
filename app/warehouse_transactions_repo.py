from .db import get_connection

_TXN_COLUMNS = """
    t.*,
    creator.name AS createdByName,
    verifier.name AS verifiedByName,
    finisher.name AS finishedByName
"""

_TXN_FROM = """
    FROM tbl_warehouse_transactions t
    LEFT JOIN tbl_users creator ON creator.id = t.createdBy
    LEFT JOIN tbl_users verifier ON verifier.id = t.verifiedBy
    LEFT JOIN tbl_users finisher ON finisher.id = t.finishedBy
"""


def _filter_clauses(search, direction, status):
    sql = " WHERE t.isDeleted = 0"
    params = []
    if direction:
        sql += " AND t.direction = %s"
        params.append(direction)
    if status:
        sql += " AND t.status = %s"
        params.append(status)
    if search:
        # t.poNumber/siNumber/drNumber/careTo cover the header; the EXISTS covers a line
        # item's description, which has no rollup column on the header to search instead.
        sql += """ AND (
            t.poNumber LIKE %s OR t.siNumber LIKE %s OR t.drNumber LIKE %s
            OR t.careTo LIKE %s OR t.branch LIKE %s OR CAST(t.id AS CHAR) LIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_warehouse_transaction_items i
                WHERE i.transactionId = t.id AND i.description LIKE %s
            )
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like, like, like, like]
    return sql, params


def count_transactions(search=None, direction=None, status=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n" + _TXN_FROM
            extra_sql, params = _filter_clauses(search, direction, status)
            cur.execute(sql + extra_sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_transactions(search=None, direction=None, status=None, limit=None, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT " + _TXN_COLUMNS + _TXN_FROM
            extra_sql, params = _filter_clauses(search, direction, status)
            sql += extra_sql + " ORDER BY t.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params = params + [int(limit), int(offset)]
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_transaction(txn_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _TXN_COLUMNS + _TXN_FROM + " WHERE t.id = %s LIMIT 1",
                (txn_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_transaction(data, created_by):
    """Insert the transaction header and its line items in one transaction.

    Same explicit-transaction pattern as create_purchase_order/create_fuel_po (this
    codebase's fourth), for a related but distinct reason: there's no money on this table
    to drift, but a transaction with zero surviving line items would be a meaningless "0
    items moved" record, so the header and its items must land together or not at all.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_warehouse_transactions
                    (direction, reason, careTo, note, status,
                     purchaseOrderId, poNumber, siNumber, customerPo, supplierInvoice,
                     drNumber, supplierDrNumber, branch,
                     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, %s, %s, %s, 'Created',
                     %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     0, %s, NOW(), %s, NOW())
                """,
                (
                    data["direction"],
                    data["reason"],
                    data["careTo"],
                    data["note"],
                    data["purchaseOrderId"],
                    data["poNumber"],
                    data["siNumber"],
                    data["customerPo"],
                    data["supplierInvoice"],
                    data["drNumber"],
                    data["supplierDrNumber"],
                    data["branch"],
                    created_by,
                    created_by,
                ),
            )
            transaction_id = cur.lastrowid

            for seq, item in enumerate(data["items"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_warehouse_transaction_items
                        (transactionId, sequence, itemId, catalogCode, description, unit,
                         category, quantity, lot, expiryDate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        transaction_id,
                        seq,
                        item["itemId"],
                        item["catalogCode"],
                        item["description"],
                        item["unit"],
                        item["category"],
                        item["quantity"],
                        item["lot"],
                        item["expiryDate"],
                    ),
                )

        conn.commit()
        return transaction_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_transaction(txn_id, data, updated_by):
    """Replace the header fields and every line item in one transaction.

    Editing is only ever offered for a still-'Created' record (enforced by the route, not
    here) - a Verified/Finished transaction represents a physical event that already
    happened, so rewriting its items after the fact would misrepresent history. Items are
    fully replaced (delete-then-reinsert) rather than diffed, matching how the Add form
    always submits a complete list rather than incremental changes - same reasoning as
    create_transaction's all-or-nothing insert.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_warehouse_transactions
                SET direction = %s, reason = %s, careTo = %s, note = %s,
                    purchaseOrderId = %s, poNumber = %s, siNumber = %s, customerPo = %s,
                    supplierInvoice = %s, drNumber = %s, supplierDrNumber = %s, branch = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (
                    data["direction"],
                    data["reason"],
                    data["careTo"],
                    data["note"],
                    data["purchaseOrderId"],
                    data["poNumber"],
                    data["siNumber"],
                    data["customerPo"],
                    data["supplierInvoice"],
                    data["drNumber"],
                    data["supplierDrNumber"],
                    data["branch"],
                    updated_by,
                    txn_id,
                ),
            )

            cur.execute("DELETE FROM tbl_warehouse_transaction_items WHERE transactionId = %s", (txn_id,))

            for seq, item in enumerate(data["items"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_warehouse_transaction_items
                        (transactionId, sequence, itemId, catalogCode, description, unit,
                         category, quantity, lot, expiryDate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        txn_id,
                        seq,
                        item["itemId"],
                        item["catalogCode"],
                        item["description"],
                        item["unit"],
                        item["category"],
                        item["quantity"],
                        item["lot"],
                        item["expiryDate"],
                    ),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_last_supplier_invoice_by_supplier():
    """The highest purely-numeric supplierInvoice recorded so far for each supplier
    (via the linked Purchase Order), so the Add form can suggest the next one. Supplier
    invoice numbers are the SUPPLIER's own numbering, not ours, so this is scoped per
    supplier - a global max would suggest a nonsense value for the next supplier picked
    (one supplier's invoices run ~955000000, another's run ~180822000000).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT po.supplierId, MAX(CAST(wt.supplierInvoice AS UNSIGNED)) AS lastNumber
                FROM tbl_warehouse_transactions wt
                JOIN tbl_purchase_orders po ON po.id = wt.purchaseOrderId
                WHERE wt.supplierInvoice REGEXP '^[0-9]+$' AND wt.isDeleted = 0
                GROUP BY po.supplierId
                """
            )
            return {row["supplierId"]: row["lastNumber"] for row in cur.fetchall()}
    finally:
        conn.close()


def list_items_for_transactions(txn_ids):
    """Every line item for a page of transactions, keyed by transactionId. Always exactly
    one query no matter how many transactions are on the page - same shape as
    purchase_orders_repo.list_items_for_purchase_orders."""
    txn_ids = [int(i) for i in txn_ids]  # coerce BEFORE interpolating placeholders
    if not txn_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(txn_ids))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM tbl_warehouse_transaction_items
                WHERE transactionId IN ({placeholders})
                ORDER BY transactionId ASC, sequence ASC
                """,
                txn_ids,
            )
            items = cur.fetchall()
    finally:
        conn.close()

    items_by_txn = {}
    for item in items:
        items_by_txn.setdefault(item["transactionId"], []).append(item)
    return items_by_txn


def get_items_for_transaction(txn_id):
    """One transaction's items - thin wrapper so single-record callers don't build a list."""
    return list_items_for_transactions([txn_id]).get(int(txn_id), [])


def soft_delete_transaction(txn_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_warehouse_transactions SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, txn_id),
            )
    finally:
        conn.close()


def verify(txn_id, verified_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_warehouse_transactions
                SET status = 'Verified', verifiedBy = %s, verifiedAt = NOW(),
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (verified_by, verified_by, txn_id),
            )
    finally:
        conn.close()


def finish(txn_id, finished_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_warehouse_transactions
                SET status = 'Finished', finishedBy = %s, finishedAt = NOW(),
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (finished_by, finished_by, txn_id),
            )
    finally:
        conn.close()


def list_stock_balances():
    """On-hand quantity per (item, branch, lot, expiry), computed fresh from Finished
    transactions - never stored. Only 'Finished' counts: Created/Verified movements
    haven't been confirmed as physically real yet, so they shouldn't move what's shown as
    available. Each group is clamped to a floor of zero individually (GREATEST, not after
    summing across lots) so one over-issued lot can't be net-cancelled into invisibility
    by a healthy lot of the same item - the legacy snapshot had 13 such negative lots,
    real evidence of historical over-issuance that a naive item-level SUM would hide.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    wi.itemId,
                    COALESCE(inv.catalog, wi.catalogCode) AS catalogCode,
                    COALESCE(inv.description, wi.description) AS description,
                    COALESCE(inv.category, wi.category) AS category,
                    wi.unit,
                    wt.branch,
                    wi.lot,
                    wi.expiryDate,
                    GREATEST(0, COALESCE(SUM(
                        CASE WHEN wt.direction = 'IN' THEN wi.quantity ELSE -wi.quantity END
                    ), 0)) AS onHand
                FROM tbl_warehouse_transaction_items wi
                JOIN tbl_warehouse_transactions wt ON wt.id = wi.transactionId
                LEFT JOIN tbl_inventory_items inv ON inv.id = wi.itemId
                WHERE wt.status = 'Finished' AND wt.isDeleted = 0
                GROUP BY wi.itemId, catalogCode, description, category, wi.unit,
                         wt.branch, wi.lot, wi.expiryDate
                ORDER BY catalogCode ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()
