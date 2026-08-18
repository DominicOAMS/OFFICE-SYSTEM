from .db import get_connection


def list_approvers():
    return _list_by_role("Approver")


def list_final_approvers():
    return _list_by_role("Final Approver")


def _list_by_role(role):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT fa.id, fa.userId, fa.role, u.name, u.email
                FROM tbl_fuel_po_approvers fa
                JOIN tbl_users u ON u.id = fa.userId
                WHERE fa.isDeleted = 0 AND fa.role = %s AND u.isDeleted = 0
                ORDER BY u.name ASC
                """,
                (role,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def is_approver(user_id):
    return _has_role(user_id, "Approver")


def is_final_approver(user_id):
    return _has_role(user_id, "Final Approver")


def _has_role(user_id, role):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM tbl_fuel_po_approvers WHERE userId = %s AND role = %s AND isDeleted = 0 LIMIT 1",
                (user_id, role),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def add_approver(user_id, role, created_by):
    """Insert a new (userId, role) link, or reactivate one that was previously
    removed - userId+role is unique, so a removed-then-re-added user reuses
    their original row instead of colliding with it."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, isDeleted FROM tbl_fuel_po_approvers WHERE userId = %s AND role = %s LIMIT 1",
                (user_id, role),
            )
            existing = cur.fetchone()
            if existing and existing["isDeleted"]:
                cur.execute(
                    "UPDATE tbl_fuel_po_approvers SET isDeleted = 0, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                    (created_by, existing["id"]),
                )
                return existing["id"]
            if existing:
                return existing["id"]
            cur.execute(
                """
                INSERT INTO tbl_fuel_po_approvers
                    (userId, role, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, %s, 0, %s, NOW(), %s, NOW())
                """,
                (user_id, role, created_by, created_by),
            )
            return cur.lastrowid
    finally:
        conn.close()


def remove_approver(approver_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_fuel_po_approvers SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, approver_id),
            )
    finally:
        conn.close()
