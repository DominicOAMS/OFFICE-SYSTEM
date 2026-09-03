import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "db_os_2026")

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD is not set. Create a .env file in the project root with DB_PASSWORD=<your-mysql-password> "
        "(see .env.example)."
    )


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=True,
    )


@contextmanager
def get_cursor():
    """A connection + cursor for a single autocommitted statement (or batch of
    statements not needing cross-table atomicity). Functions that need explicit
    transaction control (conn.begin()/commit()/rollback()) still take get_connection()
    directly - this is only for the single-connection get/count/list/update shape."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()
