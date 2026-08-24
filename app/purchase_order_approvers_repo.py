from .db import get_connection


def list_approvers():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pa.id, pa.userId, u.name, u.email
                FROM tbl_purchase_order_approvers pa
                JOIN tbl_users u ON u.id = pa.userId
                WHERE pa.isDeleted = 0 AND u.isDeleted = 0
                ORDER BY u.name ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def is_approver(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM tbl_purchase_order_approvers WHERE userId = %s AND isDeleted = 0 LIMIT 1",
                (user_id,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def add_approver(user_id, created_by):
    """Insert a new approver, or reactivate one that was previously removed -
    userId is unique, so a removed-then-re-added user reuses their original
    row instead of colliding with it."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, isDeleted FROM tbl_purchase_order_approvers WHERE userId = %s LIMIT 1",
                (user_id,),
            )
            existing = cur.fetchone()
            if existing and existing["isDeleted"]:
                cur.execute(
                    "UPDATE tbl_purchase_order_approvers SET isDeleted = 0, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                    (created_by, existing["id"]),
                )
                return existing["id"]
            if existing:
                return existing["id"]
            cur.execute(
                """
                INSERT INTO tbl_purchase_order_approvers
                    (userId, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, 0, %s, NOW(), %s, NOW())
                """,
                (user_id, created_by, created_by),
            )
            return cur.lastrowid
    finally:
        conn.close()


def remove_approver(approver_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_purchase_order_approvers SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, approver_id),
            )
    finally:
        conn.close()
