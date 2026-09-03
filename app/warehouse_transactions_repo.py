from .db import get_connection, get_cursor

_TXN_COLUMNS = """
    t.*,
    creator.name AS createdByName,
    verifier.name AS verifiedByName,
    finisher.name AS finishedByName,
    voider.name AS voidedByName
"""

_TXN_FROM = """
    FROM tbl_warehouse_transactions t
    LEFT JOIN tbl_users creator ON creator.id = t.createdBy
    LEFT JOIN tbl_users verifier ON verifier.id = t.verifiedBy
    LEFT JOIN tbl_users finisher ON finisher.id = t.finishedBy
    LEFT JOIN tbl_users voider ON voider.id = t.voidedBy
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
    with get_cursor() as cur:
        sql = "SELECT COUNT(*) AS n" + _TXN_FROM
        extra_sql, params = _filter_clauses(search, direction, status)
        cur.execute(sql + extra_sql, params)
        return cur.fetchone()["n"]


def list_transactions(search=None, direction=None, status=None, limit=None, offset=0):
    with get_cursor() as cur:
        sql = "SELECT " + _TXN_COLUMNS + _TXN_FROM
        extra_sql, params = _filter_clauses(search, direction, status)
        sql += extra_sql + " ORDER BY t.id DESC"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params = params + [int(limit), int(offset)]
        cur.execute(sql, params)
        return cur.fetchall()


def get_transaction(txn_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _TXN_COLUMNS + _TXN_FROM + " WHERE t.id = %s LIMIT 1",
            (txn_id,),
        )
        return cur.fetchone()


def insert_transaction(cur, data, created_by):
    """The header + line-item INSERTs, on a cursor the CALLER owns and will commit.

    Extracted from create_transaction so invoices_repo.create_invoice() can land an
    invoice, its items, and this transaction in ONE transaction on ONE connection - a
    linked Stock Out must not survive an invoice that rolled back, and its invoiceId FK
    can't resolve against an invoice that hasn't committed yet on a different connection.
    data["items"] may be a superset of what's read here (invoices_repo's item dicts also
    carry unitPrice/amount) - only the keys below are used.
    """
    cur.execute(
        """
        INSERT INTO tbl_warehouse_transactions
            (direction, reason, careTo, note, status,
             purchaseOrderId, poNumber, invoiceId, siNumber, customerPo, supplierInvoice,
             drNumber, supplierDrNumber, branch,
             isDeleted, createdBy, createdAt, updatedBy, updatedAt)
        VALUES
            (%s, %s, %s, %s, 'Created',
             %s, %s, %s, %s, %s, %s,
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
            data["invoiceId"],
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
                 category, quantity, enteredQuantity, enteredPackSize, lot, expiryDate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                item["enteredQuantity"],
                item["enteredPackSize"],
                item["lot"],
                item["expiryDate"],
            ),
        )

    return transaction_id


def replace_transaction_items(cur, txn_id, items):
    """Delete-then-reinsert a transaction's line items, on the caller's cursor. Extracted
    from update_transaction for the same reason as insert_transaction - invoices_repo needs
    to rewrite a linked transaction's items in the same commit as the invoice's own."""
    cur.execute("DELETE FROM tbl_warehouse_transaction_items WHERE transactionId = %s", (txn_id,))
    for seq, item in enumerate(items, start=1):
        cur.execute(
            """
            INSERT INTO tbl_warehouse_transaction_items
                (transactionId, sequence, itemId, catalogCode, description, unit,
                 category, quantity, enteredQuantity, enteredPackSize, lot, expiryDate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                item["enteredQuantity"],
                item["enteredPackSize"],
                item["lot"],
                item["expiryDate"],
            ),
        )


def create_transaction(data, created_by):
    """Insert the transaction header and its line items in one transaction.

    Same explicit-transaction pattern as create_purchase_order/create_fuel_po (this
    codebase's fourth), for a related but distinct reason: there's no money on this table
    to drift, but a transaction with zero surviving line items would be a meaningless "0
    items moved" record, so the header and its items must land together or not at all.
    Owns the connection; delegates the SQL to insert_transaction so invoices_repo can reuse
    it on a connection IT owns instead.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            transaction_id = insert_transaction(cur, data, created_by)
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

    invoiceId is deliberately NOT in this UPDATE's SET list - the link is set once at
    creation, not a form field, and the Warehouse Transactions edit form never posts it.
    Including it here would silently null the link the first time someone edits an
    invoice-linked transaction from this page.
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

            replace_transaction_items(cur, txn_id, data["items"])

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
    with get_cursor() as cur:
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


def list_items_for_transactions(txn_ids):
    """Every line item for a page of transactions, keyed by transactionId. Always exactly
    one query no matter how many transactions are on the page - same shape as
    purchase_orders_repo.list_items_for_purchase_orders."""
    txn_ids = [int(i) for i in txn_ids]  # coerce BEFORE interpolating placeholders
    if not txn_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(txn_ids))

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM tbl_warehouse_transaction_items
            WHERE transactionId IN ({placeholders})
            ORDER BY transactionId ASC, sequence ASC
            """,
            txn_ids,
        )
        items = cur.fetchall()

    items_by_txn = {}
    for item in items:
        items_by_txn.setdefault(item["transactionId"], []).append(item)
    return items_by_txn


def get_items_for_transaction(txn_id):
    """One transaction's items - thin wrapper so single-record callers don't build a list."""
    return list_items_for_transactions([txn_id]).get(int(txn_id), [])


def list_transactions_for_invoices(invoice_ids):
    """Every warehouse transaction linked to a page of invoices, keyed by invoiceId. Many
    transactions -> one invoice (a handful of legacy invoices have up to 7), which is why
    the link lives as invoiceId on this table rather than as a column on tbl_invoices."""
    invoice_ids = [int(i) for i in invoice_ids]  # coerce BEFORE interpolating placeholders
    if not invoice_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(invoice_ids))

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT id, invoiceId, direction, status, createdAt
            FROM tbl_warehouse_transactions
            WHERE invoiceId IN ({placeholders}) AND isDeleted = 0
            ORDER BY id ASC
            """,
            invoice_ids,
        )
        rows = cur.fetchall()

    txns_by_invoice = {}
    for row in rows:
        txns_by_invoice.setdefault(row["invoiceId"], []).append(row)
    return txns_by_invoice


def mark_void(cur, txn_id, voided_by, reason):
    """The Void UPDATE, on a cursor the caller owns/commits - extracted so
    invoices_repo.void_invoice() can void every transaction linked to an invoice in the
    same commit as the invoice itself. See void() for why Void has no status restriction."""
    cur.execute(
        """
        UPDATE tbl_warehouse_transactions
        SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
            updatedBy = %s, updatedAt = NOW()
        WHERE id = %s
        """,
        (voided_by, reason, voided_by, txn_id),
    )


def void(txn_id, voided_by, reason):
    """Mark a transaction Void - the only way to cancel one. There is deliberately no
    delete for this module: a stock movement record needs to stay in the ledger for audit
    purposes even when it turns out to be wrong, the same way a paper transaction gets
    voided rather than torn up. Works at any prior status, including 'Finished' - that's
    the actual point of Void existing separately from the Created-only Edit gate: it's the
    one way to correct an already-Finished transaction, and because list_stock_balances()
    only counts status='Finished' rows, voiding one automatically removes it from computed
    on-hand quantities without any other code needing to change.
    """
    with get_cursor() as cur:
        mark_void(cur, txn_id, voided_by, reason)


def verify(txn_id, verified_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_warehouse_transactions
            SET status = 'Verified', verifiedBy = %s, verifiedAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (verified_by, verified_by, txn_id),
        )


def finish(txn_id, finished_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_warehouse_transactions
            SET status = 'Finished', finishedBy = %s, finishedAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (finished_by, finished_by, txn_id),
        )


def list_stock_balances():
    """On-hand quantity per (item, branch, lot, expiry), computed fresh from Finished
    transactions - never stored. Only 'Finished' counts: Created/Verified movements
    haven't been confirmed as physically real yet, so they shouldn't move what's shown as
    available. Each group is clamped to a floor of zero individually (GREATEST, not after
    summing across lots) so one over-issued lot can't be net-cancelled into invisibility
    by a healthy lot of the same item - the legacy snapshot had 13 such negative lots,
    real evidence of historical over-issuance that a naive item-level SUM would hide.
    """
    with get_cursor() as cur:
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
