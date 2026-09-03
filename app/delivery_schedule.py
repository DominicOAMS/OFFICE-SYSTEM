"""Delivery > Schedules - a calendar computed from Delivery Receipt's own delivery dates,
plus a look at invoices still waiting on one. Not a `_repo.py` - like reports.py, it composes
existing data rather than owning a table of its own.
"""
import calendar

from . import invoices_repo
from .db import get_connection


def get_calendar_month(year, month):
    """Every delivery receipt due/delivered that month, grouped by day. A day with no
    deliveries simply has no key - callers use dict.get(day, [])."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.drNumber, r.deliveryDate, r.deliveredTo, r.status
                FROM tbl_delivery_receipts r
                WHERE r.isDeleted = 0 AND r.deliveryDate IS NOT NULL
                  AND YEAR(r.deliveryDate) = %s AND MONTH(r.deliveryDate) = %s
                ORDER BY r.deliveryDate ASC, r.drNumber ASC
                """,
                (year, month),
            )
            by_day = {}
            for row in cur.fetchall():
                by_day.setdefault(row["deliveryDate"].day, []).append(row)
            return by_day
    finally:
        conn.close()


def list_invoices_awaiting_delivery():
    """Invoices already Printed but not yet marked Delivered - using Invoices' own status is
    simpler and just as meaningful as chaining through Delivery Receipt -> Warehouse
    Transaction -> Invoice to check the same thing."""
    return invoices_repo.list_invoices(status="Printed", limit=None)


def month_grid(year, month):
    """Weeks of (day-number-or-None) for a plain calendar table - Monday-first, matching
    calendar.monthcalendar's default."""
    return calendar.monthcalendar(year, month)
