from werkzeug.security import generate_password_hash

from .db import get_cursor
from .security import generate_temp_password


def find_active_by_email(email):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM tbl_users WHERE email = %s AND isDeleted = 0 LIMIT 1",
            (email,),
        )
        return cur.fetchone()


def list_active_users():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_users WHERE isDeleted = 0 ORDER BY id ASC")
        return cur.fetchall()


def list_distinct_positions():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT position FROM tbl_users
            WHERE isDeleted = 0 AND position IS NOT NULL AND position <> ''
            ORDER BY position ASC
            """
        )
        return [row["position"] for row in cur.fetchall()]


def list_distinct_branches():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT branch FROM tbl_users
            WHERE isDeleted = 0 AND branch IS NOT NULL AND branch <> ''
            """
        )
        rows = cur.fetchall()

    tokens = set()
    for row in rows:
        for token in row["branch"].split(","):
            token = token.strip()
            if token:
                tokens.add(token)
    return sorted(tokens)


def get_user(user_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_users WHERE id = %s LIMIT 1", (user_id,))
        return cur.fetchone()


def create_user(data, created_by):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO tbl_users
                (name, email, password, mustChangePassword, position, collector, privileges, branch,
                 isDeleted, createdBy, createdAt, updatedBy, updatedAt)
            VALUES
                (%s, %s, %s, 1, %s, %s, %s, %s,
                 0, %s, NOW(), %s, NOW())
            """,
            (
                data["name"],
                data["email"],
                generate_password_hash(data["password"]),
                data["position"],
                data["collector"],
                data["privileges"],
                data["branch"],
                created_by,
                created_by,
            ),
        )
        return cur.lastrowid


def update_user(user_id, data, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_users
            SET name = %s, email = %s, position = %s,
                collector = %s, privileges = %s, branch = %s,
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (
                data["name"],
                data["email"],
                data["position"],
                data["collector"],
                data["privileges"],
                data["branch"],
                updated_by,
                user_id,
            ),
        )


def soft_delete_user(user_id, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_users
            SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (updated_by, user_id),
        )


def set_password(user_id, new_password, updated_by, must_change_password=False):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_users
            SET password = %s, mustChangePassword = %s, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (generate_password_hash(new_password), 1 if must_change_password else 0, updated_by, user_id),
        )


def reset_password(user_id, updated_by):
    temp_password = generate_temp_password()
    set_password(user_id, temp_password, updated_by, must_change_password=True)
    return temp_password
