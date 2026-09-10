from .db import get_cursor


def create_notification(user_id, title, body, url):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO tbl_notifications (userId, title, body, url) VALUES (%s, %s, %s, %s)",
            (user_id, title, body, url),
        )


def list_for_user(user_id, limit=20):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM tbl_notifications
            WHERE userId = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return cur.fetchall()


def count_unread(user_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM tbl_notifications WHERE userId = %s AND isRead = 0",
            (user_id,),
        )
        return cur.fetchone()["n"]


def mark_read(notification_id, user_id):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tbl_notifications SET isRead = 1 WHERE id = %s AND userId = %s",
            (notification_id, user_id),
        )


def mark_all_read(user_id):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tbl_notifications SET isRead = 1 WHERE userId = %s AND isRead = 0",
            (user_id,),
        )
