"""Dashboard stats - real numbers pulled straight from the database.

Not a `_repo.py` for one table - this reads a handful of aggregate numbers across every
module for the landing page, which loads on every login/navigation, so it uses targeted
COUNT/SUM queries rather than reusing each module's big `list_X(limit=None)` fetch-everything
functions (fine for a one-off Reports export click, too much for a page that loads
constantly).
"""
from datetime import date

from .db import get_connection


def get_dashboard_stats():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            month_start = date.today().replace(day=1)

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_invoices "
                "WHERE isDeleted = 0 AND invoiceDate >= %s",
                (month_start,),
            )
            invoices_this_month = cur.fetchone()["n"]

            # Counts, not peso totals - a dashboard shouldn't broadcast how much money is
            # owed to/by the business to anyone who glances at a screen.
            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_invoices "
                "WHERE isDeleted = 0 AND status NOT IN ('Paid', 'Void')"
            )
            outstanding_receivables_count = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_account_payables "
                "WHERE isDeleted = 0 AND status = 'Verified'"
            )
            outstanding_payables_count = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_inventory_items WHERE isDeleted = 0 AND status = 'AC'"
            )
            active_stock_items = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_purchase_orders "
                "WHERE isDeleted = 0 AND status = 'Pending Approval'"
            )
            pos_pending_approval = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_fuel_pos "
                "WHERE isDeleted = 0 AND status = 'Pending Approval'"
            )
            fuel_pos_pending_approval = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_account_payables "
                "WHERE isDeleted = 0 AND status = 'Created'"
            )
            payables_to_verify = cur.fetchone()["n"]

            cur.execute(
                "SELECT COUNT(*) AS n FROM tbl_check_vouchers "
                "WHERE isDeleted = 0 AND status IN ('Prepared', 'Checked')"
            )
            vouchers_to_process = cur.fetchone()["n"]

            return {
                "invoices_this_month": invoices_this_month,
                "outstanding_receivables_count": outstanding_receivables_count,
                "outstanding_payables_count": outstanding_payables_count,
                "active_stock_items": active_stock_items,
                "pos_pending_approval": pos_pending_approval,
                "fuel_pos_pending_approval": fuel_pos_pending_approval,
                "payables_to_verify": payables_to_verify,
                "vouchers_to_process": vouchers_to_process,
            }
    finally:
        conn.close()
