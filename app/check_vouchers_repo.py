from datetime import date
from decimal import Decimal

from .db import get_connection, get_cursor

_VOUCHER_COLUMNS = """
    cv.*,
    sup.code AS supplierCode,
    creator.name AS createdByName,
    checker.name AS checkedByName,
    approver.name AS approvedByName,
    payer.name AS paidByName,
    voider.name AS voidedByName
"""

_VOUCHER_FROM = """
    FROM tbl_check_vouchers cv
    JOIN tbl_suppliers sup ON sup.id = cv.supplierId
    LEFT JOIN tbl_users creator ON creator.id = cv.createdBy
    LEFT JOIN tbl_users checker ON checker.id = cv.checkedBy
    LEFT JOIN tbl_users approver ON approver.id = cv.approvedBy
    LEFT JOIN tbl_users payer ON payer.id = cv.paidBy
    LEFT JOIN tbl_users voider ON voider.id = cv.voidedBy
"""


def _filter_clauses(search, status):
    sql = " WHERE cv.isDeleted = 0"
    params = []
    if status:
        sql += " AND cv.status = %s"
        params.append(status)
    if search:
        sql += " AND (cv.voucherNumber LIKE %s OR cv.payeeName LIKE %s)"
        like = "%" + search + "%"
        params += [like, like]
    return sql, params


def count_vouchers(search=None, status=None):
    with get_cursor() as cur:
        sql = "SELECT COUNT(*) AS n" + _VOUCHER_FROM
        extra_sql, params = _filter_clauses(search, status)
        cur.execute(sql + extra_sql, params)
        return cur.fetchone()["n"]


def list_vouchers(search=None, status=None, limit=None, offset=0):
    with get_cursor() as cur:
        sql = "SELECT " + _VOUCHER_COLUMNS + _VOUCHER_FROM
        extra_sql, params = _filter_clauses(search, status)
        sql += extra_sql + " ORDER BY cv.id DESC"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params = params + [int(limit), int(offset)]
        cur.execute(sql, params)
        return cur.fetchall()


def get_voucher(voucher_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _VOUCHER_COLUMNS + _VOUCHER_FROM + " WHERE cv.id = %s LIMIT 1",
            (voucher_id,),
        )
        return cur.fetchone()


def list_payables_for_vouchers(voucher_ids):
    """Batched linked-payables lookup for the list page's View modals - one query for
    however many vouchers are on the current page, mirrors
    invoices_repo.list_items_for_invoices."""
    if not voucher_ids:
        return {}
    with get_cursor() as cur:
        placeholders = ",".join(["%s"] * len(voucher_ids))
        cur.execute(
            f"""
            SELECT cvp.voucherId, ap.*
            FROM tbl_check_voucher_payables cvp
            JOIN tbl_account_payables ap ON ap.id = cvp.payableId
            WHERE cvp.voucherId IN ({placeholders})
            ORDER BY ap.id ASC
            """,
            voucher_ids,
        )
        result = {}
        for row in cur.fetchall():
            result.setdefault(row["voucherId"], []).append(row)
        return result


def _next_voucher_number(cur, year):
    prefix = f"CV-{year}-"
    cur.execute(
        """
        SELECT MAX(CAST(SUBSTRING(voucherNumber, 9) AS UNSIGNED)) AS maxSeq
        FROM tbl_check_vouchers
        WHERE voucherNumber LIKE %s
        """,
        (prefix + "%",),
    )
    next_seq = (cur.fetchone()["maxSeq"] or 0) + 1
    return f"{prefix}{next_seq:04d}"


def create_voucher(data, created_by):
    """Opens its own connection/transaction - the header's totals are computed from the
    selected payables, and each one is re-validated (still Verified, still unclaimed)
    with a row lock immediately before the junction rows are inserted, so a payable
    claimed by a concurrent voucher between page-load and submit fails loudly here
    rather than silently getting double-booked."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            payable_ids = data["payableIds"]
            placeholders = ",".join(["%s"] * len(payable_ids))
            cur.execute(
                f"""
                SELECT ap.id, ap.supplierId, ap.amount, ap.ewtAmount, ap.vatableAmount,
                       ap.vatAmount, ap.netAmount, ap.status,
                       (SELECT cv.id FROM tbl_check_voucher_payables cvp
                        JOIN tbl_check_vouchers cv ON cv.id = cvp.voucherId
                        WHERE cvp.payableId = ap.id AND cv.status != 'Void' LIMIT 1) AS claimedBy
                FROM tbl_account_payables ap
                WHERE ap.id IN ({placeholders})
                FOR UPDATE
                """,
                payable_ids,
            )
            rows = cur.fetchall()
            if len(rows) != len(payable_ids):
                raise ValueError("One or more selected payables no longer exist.")
            for row in rows:
                if row["status"] != "Verified":
                    raise ValueError(f"Payable #{row['id']} is no longer Verified.")
                if row["claimedBy"]:
                    raise ValueError(f"Payable #{row['id']} is already linked to another voucher.")
                if row["supplierId"] != data["supplierId"]:
                    raise ValueError(f"Payable #{row['id']} belongs to a different supplier.")

            total_amount = sum((r["amount"] for r in rows), Decimal("0.00"))
            vatable_amount = sum((r["vatableAmount"] for r in rows), Decimal("0.00"))
            vat_amount = sum((r["vatAmount"] for r in rows), Decimal("0.00"))
            total_ewt_amount = sum((r["ewtAmount"] for r in rows), Decimal("0.00"))
            net_amount = sum((r["netAmount"] for r in rows), Decimal("0.00"))

            voucher_number = _next_voucher_number(cur, date.today().year)
            cur.execute(
                """
                INSERT INTO tbl_check_vouchers
                    (voucherNumber, supplierId, payeeName, payeeAddress, payeeTin,
                     voucherDate, dueDate, totalAmount, vatableAmount, vatAmount,
                     totalEwtAmount, netAmount, remarksHeading, remarks, status, createdBy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Prepared', %s)
                """,
                (
                    voucher_number, data["supplierId"], data["payeeName"], data["payeeAddress"],
                    data["payeeTin"], data["voucherDate"], data["dueDate"], total_amount,
                    vatable_amount, vat_amount, total_ewt_amount, net_amount,
                    data["remarksHeading"], data["remarks"], created_by,
                ),
            )
            voucher_id = cur.lastrowid
            for payable_id in payable_ids:
                cur.execute(
                    "INSERT INTO tbl_check_voucher_payables (voucherId, payableId) VALUES (%s, %s)",
                    (voucher_id, payable_id),
                )
        conn.commit()
        return voucher_id, voucher_number
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_checked(voucher_id, checked_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_check_vouchers
            SET status = 'Checked', checkedBy = %s, checkedAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (checked_by, checked_by, voucher_id),
        )


def mark_approved(voucher_id, approved_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_check_vouchers
            SET status = 'Approved', approvedBy = %s, approvedAt = NOW(),
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (approved_by, approved_by, voucher_id),
        )


def mark_paid(voucher_id, paid_by, check_number):
    """Cascades to every payable this voucher covers - same shape as
    invoices_repo.void_invoice's cascade to its linked warehouse transactions."""
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_check_vouchers
                SET status = 'Paid', paidBy = %s, paidAt = NOW(),
                    checkNumber = COALESCE(%s, checkNumber),
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (paid_by, check_number, paid_by, voucher_id),
            )
            cur.execute(
                """
                UPDATE tbl_account_payables ap
                JOIN tbl_check_voucher_payables cvp ON cvp.payableId = ap.id
                SET ap.status = 'Paid', ap.updatedBy = %s, ap.updatedAt = NOW()
                WHERE cvp.voucherId = %s
                """,
                (paid_by, voucher_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void(voucher_id, voided_by, reason):
    """No cascade needed - a payable's "claimed" status is computed live off whether
    its voucher is non-Void, not stored redundantly on the payable row, so voiding here
    automatically frees every linked payable to be picked by a new voucher."""
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_check_vouchers
            SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (voided_by, reason, voided_by, voucher_id),
        )
