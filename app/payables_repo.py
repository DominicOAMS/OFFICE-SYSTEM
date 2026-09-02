from .db import get_connection

_PAYABLE_COLUMNS = """
    ap.*,
    sup.code AS supplierCode,
    creator.name AS createdByName,
    verifier.name AS verifiedByName,
    voider.name AS voidedByName,
    claim.voucherId AS claimedByVoucherId,
    claim.voucherNumber AS claimedByVoucherNumber
"""

_PAYABLE_FROM = """
    FROM tbl_account_payables ap
    JOIN tbl_suppliers sup ON sup.id = ap.supplierId
    LEFT JOIN tbl_users creator ON creator.id = ap.createdBy
    LEFT JOIN tbl_users verifier ON verifier.id = ap.verifiedBy
    LEFT JOIN tbl_users voider ON voider.id = ap.voidedBy
    LEFT JOIN (
        SELECT cvp.payableId, cv.id AS voucherId, cv.voucherNumber
        FROM tbl_check_voucher_payables cvp
        JOIN tbl_check_vouchers cv ON cv.id = cvp.voucherId AND cv.status != 'Void'
    ) claim ON claim.payableId = ap.id
"""


def _filter_clauses(search, status, has_po):
    sql = " WHERE ap.isDeleted = 0"
    params = []
    if has_po is True:
        sql += " AND ap.purchaseOrderId IS NOT NULL"
    elif has_po is False:
        sql += " AND ap.purchaseOrderId IS NULL"
    if status:
        sql += " AND ap.status = %s"
        params.append(status)
    if search:
        sql += """ AND (
            ap.poNumber LIKE %s OR ap.payeeName LIKE %s OR ap.siNumber LIKE %s
            OR ap.drNumber LIKE %s OR ap.referenceNumber LIKE %s OR ap.description LIKE %s
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like, like, like]
    return sql, params


def count_payables(search=None, status=None, has_po=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n" + _PAYABLE_FROM
            extra_sql, params = _filter_clauses(search, status, has_po)
            cur.execute(sql + extra_sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_payables(search=None, status=None, has_po=None, limit=None, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT " + _PAYABLE_COLUMNS + _PAYABLE_FROM
            extra_sql, params = _filter_clauses(search, status, has_po)
            sql += extra_sql + " ORDER BY ap.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params = params + [int(limit), int(offset)]
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_payable(payable_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _PAYABLE_COLUMNS + _PAYABLE_FROM + " WHERE ap.id = %s LIMIT 1",
                (payable_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def list_unclaimed_verified_for_supplier(supplier_id):
    """Feeds the Check Voucher Add form's payable picker - a Verified payable owed to
    this supplier that isn't already linked to a non-Void voucher."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ap.*, sup.code AS supplierCode
                FROM tbl_account_payables ap
                JOIN tbl_suppliers sup ON sup.id = ap.supplierId
                WHERE ap.supplierId = %s AND ap.status = 'Verified' AND ap.isDeleted = 0
                  AND ap.id NOT IN (
                      SELECT cvp.payableId FROM tbl_check_voucher_payables cvp
                      JOIN tbl_check_vouchers cv ON cv.id = cvp.voucherId
                      WHERE cv.status != 'Void'
                  )
                ORDER BY ap.id ASC
                """,
                (supplier_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def create_payable(data, created_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_account_payables
                    (purchaseOrderId, poNumber, supplierId, payeeName, payeeAddress, payeeTin,
                     siNumber, drNumber, referenceNumber, description, amount, ewtRate,
                     ewtAmount, vatableAmount, vatAmount, netAmount, status, createdBy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'Created', %s)
                """,
                (
                    data["purchaseOrderId"], data["poNumber"], data["supplierId"],
                    data["payeeName"], data["payeeAddress"], data["payeeTin"],
                    data["siNumber"], data["drNumber"], data["referenceNumber"],
                    data["description"], data["amount"], data["ewtRate"],
                    data["ewtAmount"], data["vatableAmount"], data["vatAmount"],
                    data["netAmount"], created_by,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def verify(payable_id, verified_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_account_payables
                SET status = 'Verified', verifiedBy = %s, verifiedAt = NOW(),
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (verified_by, verified_by, payable_id),
            )
    finally:
        conn.close()


def void(payable_id, voided_by, reason):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_account_payables
                SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (voided_by, reason, voided_by, payable_id),
            )
    finally:
        conn.close()
