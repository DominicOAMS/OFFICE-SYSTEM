from pymysql.err import IntegrityError

from . import warehouse_transactions_repo
from .db import get_connection, get_cursor

# Pricing is VAT-INCLUSIVE (confirmed against the legacy data: SUM(line Amount) per invoice
# equals AmountDue, not Vatable - i.e. Vatable is back-calculated as AmountDue / 1.12). This
# is the opposite convention from Purchase Orders (VAT-exclusive, correct for a supplier
# quote) - deliberate, not a copy-paste of the PO math. See routes._parse_invoice_form for
# where totalAmount/vatableAmount/vatAmount are actually computed from line items.
#
# amount on a line item is always `enteredQuantity * unitPrice` - the ENTERED quantity, not
# the base-unit-converted `quantity` - so a box price stays a box price and never gets
# divided by packSize.

_INV_COLUMNS = """
    i.*,
    creator.name AS createdByName,
    printer.name AS printedByName,
    deliverer.name AS deliveredByName,
    payer.name AS paidByName,
    voider.name AS voidedByName,
    c.code AS customerCodeCurrent,
    c.name AS customerNameCurrent
"""

_INV_FROM = """
    FROM tbl_invoices i
    LEFT JOIN tbl_users creator ON creator.id = i.createdBy
    LEFT JOIN tbl_users printer ON printer.id = i.printedBy
    LEFT JOIN tbl_users deliverer ON deliverer.id = i.deliveredBy
    LEFT JOIN tbl_users payer ON payer.id = i.paidBy
    LEFT JOIN tbl_users voider ON voider.id = i.voidedBy
    LEFT JOIN tbl_customers c ON c.id = i.customerId
"""


def _filter_clauses(search, status, branch, outstanding_only=False):
    sql = " WHERE i.isDeleted = 0"
    params = []
    if status:
        sql += " AND i.status = %s"
        params.append(status)
    if outstanding_only:
        # Feeds the Collectibles report - "still owed to us", i.e. everything short of
        # already Paid or a dead Void row. Coarser than a single status filter on purpose.
        sql += " AND i.status NOT IN ('Paid', 'Void')"
    if branch:
        sql += " AND i.branch = %s"
        params.append(branch)
    if search:
        # Header columns cover most searches; the EXISTS covers a line item's description,
        # which has no rollup column on the header to search instead.
        sql += """ AND (
            i.invoiceNumber LIKE %s OR i.soldTo LIKE %s OR i.customerCode LIKE %s
            OR i.customerPo LIKE %s OR i.noaNumber LIKE %s OR i.salesPerson LIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_invoice_items ii
                WHERE ii.invoiceId = i.id AND ii.description LIKE %s
            )
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like, like, like, like]
    return sql, params


def count_invoices(search=None, status=None, branch=None, outstanding_only=False):
    with get_cursor() as cur:
        sql = "SELECT COUNT(*) AS n" + _INV_FROM
        extra_sql, params = _filter_clauses(search, status, branch, outstanding_only)
        cur.execute(sql + extra_sql, params)
        return cur.fetchone()["n"]


def list_invoices(search=None, status=None, branch=None, limit=None, offset=0, outstanding_only=False):
    with get_cursor() as cur:
        sql = "SELECT " + _INV_COLUMNS + _INV_FROM
        extra_sql, params = _filter_clauses(search, status, branch, outstanding_only)
        sql += extra_sql + " ORDER BY i.id DESC"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params = params + [int(limit), int(offset)]
        cur.execute(sql, params)
        return cur.fetchall()


def list_invoices_for_customer(customer_id):
    """Every non-deleted invoice for one customer, unpaginated - feeds the Statement of
    Account report, where one customer's full history is always a small, boundable list
    (unlike the main Invoices page, which needs real pagination over 8,000+ rows)."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _INV_COLUMNS + _INV_FROM
            + " WHERE i.isDeleted = 0 AND i.customerId = %s ORDER BY i.invoiceDate ASC, i.id ASC",
            (customer_id,),
        )
        return cur.fetchall()


def get_invoice(invoice_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _INV_COLUMNS + _INV_FROM + " WHERE i.id = %s LIMIT 1",
            (invoice_id,),
        )
        return cur.fetchone()


def list_items_for_invoices(invoice_ids):
    """Every line item for a page of invoices, keyed by invoiceId. Always exactly one
    query no matter how many invoices are on the page - same shape as
    purchase_orders_repo.list_items_for_purchase_orders."""
    invoice_ids = [int(i) for i in invoice_ids]  # coerce BEFORE interpolating placeholders
    if not invoice_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(invoice_ids))

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM tbl_invoice_items
            WHERE invoiceId IN ({placeholders})
            ORDER BY invoiceId ASC, sequence ASC
            """,
            invoice_ids,
        )
        items = cur.fetchall()

    items_by_invoice = {}
    for item in items:
        items_by_invoice.setdefault(item["invoiceId"], []).append(item)
    return items_by_invoice


def get_items_for_invoice(invoice_id):
    """One invoice's items - thin wrapper so single-record callers don't build a list."""
    return list_items_for_invoices([invoice_id]).get(int(invoice_id), [])


def _next_invoice_number(cur):
    """Global series (not year-scoped, unlike PO numbers) - continues the legacy 7-digit
    zero-padded scheme. REGEXP excludes non-numeric invoice numbers (the one legacy
    credit-memo variant, "0207925-CM") from the max, same predicate
    list_last_supplier_invoice_by_supplier() already uses for a similar purely-numeric-only
    max. Computed inside the caller's transaction, right before the INSERT."""
    cur.execute("SELECT MAX(CAST(invoiceNumber AS UNSIGNED)) AS maxNum FROM tbl_invoices WHERE invoiceNumber REGEXP '^[0-9]+$'")
    next_num = (cur.fetchone()["maxNum"] or 0) + 1
    return f"{next_num:07d}"


def _insert_invoice(cur, invoice_number, data, created_by):
    cur.execute(
        """
        INSERT INTO tbl_invoices
            (invoiceNumber, invoiceDate, customerId, customerCode, soldTo, address, tin,
             customerPo, paymentTerms, paymentDueDate, salesPerson,
             vatableAmount, vatAmount, totalAmount, status, invoiceType, noaNumber, notes,
             branch, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
        VALUES
            (%s, COALESCE(%s, CURDATE()), %s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s, 'Created', %s, %s, %s,
             %s, 0, %s, NOW(), %s, NOW())
        """,
        (
            invoice_number,
            data["invoiceDate"],
            data["customerId"],
            data["customerCode"],
            data["soldTo"],
            data["address"],
            data["tin"],
            data["customerPo"],
            data["paymentTerms"],
            data["paymentDueDate"],
            data["salesPerson"],
            data["vatableAmount"],
            data["vatAmount"],
            data["totalAmount"],
            data["invoiceType"],
            data["noaNumber"],
            data["notes"],
            data["branch"],
            created_by,
            created_by,
        ),
    )
    invoice_id = cur.lastrowid

    for seq, item in enumerate(data["items"], start=1):
        cur.execute(
            """
            INSERT INTO tbl_invoice_items
                (invoiceId, sequence, itemId, catalogCode, description, unit, category,
                 quantity, enteredQuantity, enteredPackSize, lot, expiryDate, unitPrice, amount)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                invoice_id,
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
                item["unitPrice"],
                item["amount"],
            ),
        )

    return invoice_id


def create_invoice(data, created_by):
    """Insert the invoice header, its line items, and (when requested) a linked Warehouse
    Stock Out transaction with THAT transaction's own line items - all in one commit.

    This codebase's fifth explicit transaction, and the first spanning two modules. The
    reasons compound: (a) create_purchase_order's - vatableAmount/vatAmount/totalAmount are
    computed from data["items"] before those rows exist; (b) create_transaction's - a
    transaction with no surviving items is meaningless; and (c) new here - the transaction's
    invoiceId FK cannot resolve against an invoice that hasn't committed yet, so the two
    documents physically cannot be created on separate connections. An invoice that billed
    goods with no stock movement to match, or a Stock Out with no invoice behind it, is
    exactly the kind of drift this project's legacy migrations kept finding.

    Retries up to 3 times on a duplicate invoiceNumber (two concurrent creates can both read
    the same MAX before either commits) - a gap or a duplicate in this series is a real
    audit problem, so a retryable collision should not surface as an error to the user.
    """
    last_error = None
    for _attempt in range(3):
        conn = get_connection()
        try:
            conn.begin()
            with conn.cursor() as cur:
                invoice_number = _next_invoice_number(cur)
                invoice_id = _insert_invoice(cur, invoice_number, data, created_by)

                transaction_id = None
                if data["createStockOut"] and data["items"]:
                    transaction_id = warehouse_transactions_repo.insert_transaction(
                        cur,
                        {
                            "direction": "OUT",
                            "reason": "Invoice",
                            "careTo": data["soldTo"],
                            "note": f"Auto-created from Invoice {invoice_number}",
                            "purchaseOrderId": None,
                            "poNumber": None,
                            "invoiceId": invoice_id,
                            "siNumber": invoice_number,
                            "customerPo": data["customerPo"],
                            "supplierInvoice": None,
                            "drNumber": None,
                            "supplierDrNumber": None,
                            "branch": data["branch"],
                            "items": data["items"],
                        },
                        created_by,
                    )
            conn.commit()
            return invoice_id, invoice_number, transaction_id
        except IntegrityError as e:
            conn.rollback()
            last_error = e
            continue
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    raise last_error


def update_invoice(invoice_id, data, updated_by):
    """Rewrite the header and replace its line items, and do the same to every linked
    warehouse transaction that isn't yet Finished/Void - in one commit, so the invoice and
    its Stock Out can never disagree. The route only offers Edit while the invoice itself is
    'Created' and every linked transaction is still Created/Verified; this function trusts
    that gate rather than re-checking it, matching update_transaction's own division of
    responsibility (status enforcement lives in the route, not the repo).
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_invoices
                SET invoiceDate = COALESCE(%s, invoiceDate), customerId = %s, customerCode = %s,
                    soldTo = %s, address = %s, tin = %s, customerPo = %s, paymentTerms = %s,
                    paymentDueDate = %s, salesPerson = %s,
                    vatableAmount = %s, vatAmount = %s, totalAmount = %s,
                    invoiceType = %s, noaNumber = %s, notes = %s, branch = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (
                    data["invoiceDate"],
                    data["customerId"],
                    data["customerCode"],
                    data["soldTo"],
                    data["address"],
                    data["tin"],
                    data["customerPo"],
                    data["paymentTerms"],
                    data["paymentDueDate"],
                    data["salesPerson"],
                    data["vatableAmount"],
                    data["vatAmount"],
                    data["totalAmount"],
                    data["invoiceType"],
                    data["noaNumber"],
                    data["notes"],
                    data["branch"],
                    updated_by,
                    invoice_id,
                ),
            )

            cur.execute("DELETE FROM tbl_invoice_items WHERE invoiceId = %s", (invoice_id,))
            for seq, item in enumerate(data["items"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_invoice_items
                        (invoiceId, sequence, itemId, catalogCode, description, unit, category,
                         quantity, enteredQuantity, enteredPackSize, lot, expiryDate, unitPrice, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        invoice_id,
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
                        item["unitPrice"],
                        item["amount"],
                    ),
                )

            cur.execute(
                """
                SELECT id FROM tbl_warehouse_transactions
                WHERE invoiceId = %s AND status NOT IN ('Finished', 'Void') AND isDeleted = 0
                """,
                (invoice_id,),
            )
            for row in cur.fetchall():
                warehouse_transactions_repo.replace_transaction_items(cur, row["id"], data["items"])

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_printed(invoice_id, printed_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_invoices
            SET status = 'Printed', printedBy = %s, printedAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (printed_by, printed_by, invoice_id),
        )


def mark_delivered(invoice_id, delivered_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_invoices
            SET status = 'Delivered', deliveredBy = %s, deliveredAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (delivered_by, delivered_by, invoice_id),
        )


def mark_paid(invoice_id, paid_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_invoices
            SET status = 'Paid', paidBy = %s, paidAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (paid_by, paid_by, invoice_id),
        )


def void_invoice(invoice_id, voided_by, reason):
    """Void the invoice and every linked warehouse transaction that isn't already Void, in
    one commit - a half-applied void (invoice cancelled, stock still deducted for it) is
    exactly the kind of drift this project's migrations kept finding in legacy data. Safe
    against the legacy reversing-entry pairs too: an invoice with both a Finished OUT and a
    Finished reversing IN nets to 0 on-hand today, and voiding both still nets to 0 - no
    special-casing by direction needed, void every linked transaction that isn't Void.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute("SELECT invoiceNumber FROM tbl_invoices WHERE id = %s", (invoice_id,))
            invoice_number = cur.fetchone()["invoiceNumber"]

            cur.execute(
                """
                UPDATE tbl_invoices
                SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (voided_by, reason, voided_by, invoice_id),
            )
            cur.execute(
                "SELECT id FROM tbl_warehouse_transactions WHERE invoiceId = %s AND status != 'Void' AND isDeleted = 0",
                (invoice_id,),
            )
            for row in cur.fetchall():
                warehouse_transactions_repo.mark_void(
                    cur, row["id"], voided_by, f"Invoice {invoice_number} voided"
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
