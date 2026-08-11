"""One-off migration: hash every active user's password to the default
"password" and flag their account so they must change it on next login.
Run once with the project venv: .venv\\Scripts\\python.exe database\\reset_all_passwords.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash

from app.db import get_connection

DEFAULT_PASSWORD = "password"


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM tbl_users WHERE isDeleted = 0")
            rows = cur.fetchall()
            for row in rows:
                hashed = generate_password_hash(DEFAULT_PASSWORD)
                cur.execute(
                    "UPDATE tbl_users SET password = %s, mustChangePassword = 1 WHERE id = %s",
                    (hashed, row["id"]),
                )
            print(f"Reset password for {len(rows)} active user(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
