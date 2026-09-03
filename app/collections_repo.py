from decimal import Decimal

from .db import get_connection, get_cursor

_COLLECTION_COLUMNS = """
    col.*,
    cust.code AS liveCustomerCode,
    creator.name AS createdByName,
    voider.name AS voidedByName
"""

_COLLECTION_FROM = """
    FROM tbl_collections col
    LEFT JOIN tbl_customers cust ON cust.id = col.customerId
    LEFT JOIN tbl_users creator ON creator.id = col.createdBy
    LEFT JOIN tbl_users voider ON voider.id = col.voidedBy
"""


def _filter_clauses(search, status):
    sql = " WHERE col.isDeleted = 0"
    params = []
    if status:
        sql += " AND col.status = %s"
        params.append(status)
    if search:
        sql += " AND (col.orNumber LIKE %s OR col.customerName LIKE %s OR col.chequeNumber LIKE %s)"
        like = "%" + search + "%"
        params += [like, like, like]
    return sql, params


def count_collections(search=None, status=None):
    with get_cursor() as cur:
        sql = "SELECT COUNT(*) AS n" + _COLLECTION_FROM
        extra_sql, params = _filter_clauses(search, status)
        cur.execute(sql + extra_sql, params)
        return cur.fetchone()["n"]


def list_collections(search=None, status=None, limit=None, offset=0):
    with get_cursor() as cur:
        sql = "SELECT " + _COLLECTION_COLUMNS + _COLLECTION_FROM
        extra_sql, params = _filter_clauses(search, status)
        sql += extra_sql + " ORDER BY col.id DESC"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params = params + [int(limit), int(offset)]
        cur.execute(sql, params)
        return cur.fetchall()


def list_collections_for_customer(customer_id):
    """Every non-deleted collection for one customer, unpaginated - feeds the Statement of
    Account report alongside invoices_repo.list_invoices_for_customer."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _COLLECTION_COLUMNS + _COLLECTION_FROM
            + " WHERE col.isDeleted = 0 AND col.customerId = %s ORDER BY col.dateCollected ASC, col.id ASC",
            (customer_id,),
        )
        return cur.fetchall()


def get_collection(collection_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _COLLECTION_COLUMNS + _COLLECTION_FROM + " WHERE col.id = %s LIMIT 1",
            (collection_id,),
        )
        return cur.fetchone()


def list_invoices_for_collections(collection_ids):
    """Batched linked-invoices lookup for the list page's View modals - one query for
    however many collections are on the current page, mirrors
    check_vouchers_repo.list_payables_for_vouchers."""
    if not collection_ids:
        return {}
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(collection_ids))
        cur.execute(
            f"""
            SELECT ci.collectionId, i.*
            FROM tbl_collection_invoices ci
            JOIN tbl_invoices i ON i.id = ci.invoiceId
            WHERE ci.collectionId IN ({placeholders})
            ORDER BY i.id ASC
            """,
            collection_ids,
        )
        result = {}
        for row in cur.fetchall():
            result.setdefault(row["collectionId"], []).append(row)
        return result


def list_uncollected_delivered_invoices_for_customer(customer_id):
    """Feeds the Collection Add form's invoice picker: a customer's Delivered invoices not
    already claimed by a non-Void collection."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT i.*
            FROM tbl_invoices i
            WHERE i.customerId = %s AND i.status = 'Delivered' AND i.isDeleted = 0
              AND i.id NOT IN (
                  SELECT ci.invoiceId FROM tbl_collection_invoices ci
                  JOIN tbl_collections c ON c.id = ci.collectionId
                  WHERE c.status != 'Void'
              )
            ORDER BY i.id ASC
            """,
            (customer_id,),
        )
        return cur.fetchall()


def create_collection(data, created_by):
    """Opens its own connection/transaction - every selected invoice is re-validated (still
    Delivered, still owned by this customer, still unclaimed) with a row lock immediately
    before the junction rows are inserted, then cascaded straight to Paid in the same
    commit - there's no intermediate Collection stage to wait for, the money's already in
    hand. Mirrors check_vouchers_repo.create_voucher's shape."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            invoice_ids = data["invoiceIds"]
            placeholders = ",".join(["%s"] * len(invoice_ids))
            cur.execute(
                f"""
                SELECT id, customerId, status
                FROM tbl_invoices
                WHERE id IN ({placeholders})
                FOR UPDATE
                """,
                invoice_ids,
            )
            rows = cur.fetchall()
            if len(rows) != len(invoice_ids):
                raise ValueError("One or more selected invoices no longer exist.")
            for row in rows:
                if row["status"] != "Delivered":
                    raise ValueError(f"Invoice #{row['id']} is no longer Delivered.")
                if row["customerId"] != data["customerId"]:
                    raise ValueError(f"Invoice #{row['id']} belongs to a different customer.")

            cur.execute(
                """
                INSERT INTO tbl_collections
                    (orNumber, customerId, customerCode, customerName, dateCollected,
                     collectedBy, remittedTo, chequeNumber, chequeDate, bank,
                     bookletNumber, seriesNumber, amount, wtaxRate, wtaxAmount,
                     retentionAmount, netAmount, birFormStatus, notes, status, createdBy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, 'Created', %s)
                """,
                (
                    data["orNumber"], data["customerId"], data["customerCode"],
                    data["customerName"], data["dateCollected"], data["collectedBy"],
                    data["remittedTo"], data["chequeNumber"], data["chequeDate"], data["bank"],
                    data["bookletNumber"], data["seriesNumber"], data["amount"],
                    data["wtaxRate"], data["wtaxAmount"], data["retentionAmount"],
                    data["netAmount"], data["birFormStatus"], data["notes"], created_by,
                ),
            )
            collection_id = cur.lastrowid
            for invoice_id in invoice_ids:
                cur.execute(
                    "INSERT INTO tbl_collection_invoices (collectionId, invoiceId) VALUES (%s, %s)",
                    (collection_id, invoice_id),
                )
            cur.execute(
                f"""
                UPDATE tbl_invoices
                SET status = 'Paid', paidAt = %s, updatedBy = %s, updatedAt = NOW()
                WHERE id IN ({placeholders})
                """,
                [data["dateCollected"], created_by] + invoice_ids,
            )
        conn.commit()
        return collection_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void(collection_id, voided_by, reason):
    """Reverts every linked invoice still at Paid back to Delivered, freeing it to be
    collected again (correctly) - same "void frees what it claimed" shape as
    check_vouchers_repo.void, but with a real status reversal since Invoices (unlike
    Payables) have no separate "claimed but not yet paid" state to fall back to."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_collections
                SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (voided_by, reason, voided_by, collection_id),
            )
            cur.execute(
                """
                UPDATE tbl_invoices i
                JOIN tbl_collection_invoices ci ON ci.invoiceId = i.id
                SET i.status = 'Delivered', i.paidBy = NULL, i.paidAt = NULL,
                    i.updatedBy = %s, i.updatedAt = NOW()
                WHERE ci.collectionId = %s AND i.status = 'Paid'
                """,
                (voided_by, collection_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
