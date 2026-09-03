from .db import get_cursor

_GATEPASS_COLUMNS = """
    g.*,
    creator.name AS createdByName,
    voider.name AS voidedByName
"""

_GATEPASS_FROM = """
    FROM tbl_gatepasses g
    LEFT JOIN tbl_users creator ON creator.id = g.createdBy
    LEFT JOIN tbl_users voider ON voider.id = g.voidedBy
"""


def _filter_clauses(search, status):
    sql = " WHERE g.isDeleted = 0"
    params = []
    if status:
        sql += " AND g.status = %s"
        params.append(status)
    if search:
        sql += " AND (g.deliveryStaff LIKE %s OR g.invoicesText LIKE %s)"
        like = "%" + search + "%"
        params += [like, like]
    return sql, params


def count_gatepasses(search=None, status=None):
    with get_cursor() as cur:
        sql = "SELECT COUNT(*) AS n" + _GATEPASS_FROM
        extra_sql, params = _filter_clauses(search, status)
        cur.execute(sql + extra_sql, params)
        return cur.fetchone()["n"]


def list_gatepasses(search=None, status=None, limit=None, offset=0):
    with get_cursor() as cur:
        sql = "SELECT " + _GATEPASS_COLUMNS + _GATEPASS_FROM
        extra_sql, params = _filter_clauses(search, status)
        sql += extra_sql + " ORDER BY g.id DESC"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params = params + [int(limit), int(offset)]
        cur.execute(sql, params)
        return cur.fetchall()


def get_gatepass(gatepass_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT " + _GATEPASS_COLUMNS + _GATEPASS_FROM + " WHERE g.id = %s LIMIT 1",
            (gatepass_id,),
        )
        return cur.fetchone()


def create_gatepass(data, created_by):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO tbl_gatepasses
                (deliveryStaff, transDate, transTime, temperature, invoicesText,
                 submittedBy, checkedBy, notes, status, createdBy)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Created', %s)
            """,
            (
                data["deliveryStaff"], data["transDate"], data["transTime"],
                data["temperature"], data["invoicesText"], data["submittedBy"],
                data["checkedBy"], data["notes"], created_by,
            ),
        )
        return cur.lastrowid


def void(gatepass_id, voided_by, reason):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_gatepasses
            SET status = 'Void', voidedBy = %s, voidedAt = NOW(), voidReason = %s,
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (voided_by, reason, voided_by, gatepass_id),
        )
