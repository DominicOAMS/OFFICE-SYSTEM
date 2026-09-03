"""Reports > Downloadables - CSV export of what's already on an existing list page.

Not a `_repo.py` - it never touches the database itself, only calls into repos that already
exist and already know how to fetch/filter their own data. This module is just a registry
describing which datasets are exportable and how to turn a row dict into a CSV line.
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal

from flask import Response, abort

from . import (
    check_vouchers_repo,
    collections_repo,
    invoices_repo,
    payables_repo,
    purchase_orders_repo,
    warehouse_transactions_repo,
)

DATASETS = {
    "invoices": {
        "label": "Invoices",
        "date_field": "invoiceDate",
        "status_choices": ["Created", "Printed", "Delivered", "Paid", "Void"],
        "fetch": lambda search, status: invoices_repo.list_invoices(
            search=search, status=status, limit=None
        ),
        "columns": [
            ("Invoice #", "invoiceNumber"), ("Date", "invoiceDate"), ("Sold To", "soldTo"),
            ("Customer PO #", "customerPo"), ("Sales Person", "salesPerson"),
            ("Branch", "branch"), ("Status", "status"), ("Vatable", "vatableAmount"),
            ("VAT", "vatAmount"), ("Total", "totalAmount"),
        ],
    },
    "collections": {
        "label": "Collections",
        "date_field": "dateCollected",
        "status_choices": ["Created", "Void"],
        "fetch": lambda search, status: collections_repo.list_collections(
            search=search, status=status, limit=None
        ),
        "columns": [
            ("OR #", "orNumber"), ("Date Collected", "dateCollected"),
            ("Customer", "customerName"), ("Collected By", "collectedBy"),
            ("Cheque #", "chequeNumber"), ("Bank", "bank"), ("Amount", "amount"),
            ("WTax", "wtaxAmount"), ("Retention", "retentionAmount"),
            ("Net Amount", "netAmount"), ("Status", "status"),
        ],
    },
    "payables_po": {
        "label": "PO Payables",
        "date_field": "createdAt",
        "status_choices": ["Created", "Verified", "Paid", "Void"],
        "fetch": lambda search, status: payables_repo.list_payables(
            search=search, status=status, has_po=True, limit=None
        ),
        "columns": [
            ("PO #", "poNumber"), ("Payee", "payeeName"), ("SI #", "siNumber"),
            ("DR #", "drNumber"), ("Amount", "amount"), ("EWT", "ewtAmount"),
            ("Net Amount", "netAmount"), ("Status", "status"), ("Date", "createdAt"),
        ],
    },
    "payables_non_po": {
        "label": "Non-PO Payables",
        "date_field": "createdAt",
        "status_choices": ["Created", "Verified", "Paid", "Void"],
        "fetch": lambda search, status: payables_repo.list_payables(
            search=search, status=status, has_po=False, limit=None
        ),
        "columns": [
            ("Payee", "payeeName"), ("Description", "description"),
            ("SI #", "siNumber"), ("DR #", "drNumber"), ("Amount", "amount"),
            ("EWT", "ewtAmount"), ("Net Amount", "netAmount"), ("Status", "status"),
            ("Date", "createdAt"),
        ],
    },
    "check_vouchers": {
        "label": "Check Vouchers",
        "date_field": "voucherDate",
        "status_choices": ["Prepared", "Checked", "Approved", "Paid", "Void"],
        "fetch": lambda search, status: check_vouchers_repo.list_vouchers(
            search=search, status=status, limit=None
        ),
        "columns": [
            ("Voucher #", "voucherNumber"), ("Payee", "payeeName"),
            ("Voucher Date", "voucherDate"), ("Due Date", "dueDate"),
            ("Check #", "checkNumber"), ("Total", "totalAmount"),
            ("EWT", "totalEwtAmount"), ("Net Amount", "netAmount"), ("Status", "status"),
        ],
    },
    "purchase_orders": {
        "label": "Purchase Orders",
        "date_field": "orderDate",
        "status_choices": [
            "Draft", "Pending Approval", "Approved", "Rejected",
            # Legacy-only leftovers this table's own migration carried over verbatim
            # (no transition rule in the new workflow reaches them) - still real,
            # exportable data, so still offered as a filter option here.
            "For Approval", "For Verification", "Printed", "Partially Delivered",
            "Delivered", "Paid",
        ],
        "fetch": lambda search, status: purchase_orders_repo.list_purchase_orders(
            search=search, status=status, limit=None
        ),
        "columns": [
            ("PO #", "poNumber"), ("Order Date", "orderDate"), ("Supplier", "supplierName"),
            ("Branch", "branch"), ("Vatable", "vatableAmount"), ("VAT", "vatAmount"),
            ("Total", "totalAmount"), ("Status", "status"),
        ],
    },
    "warehouse_transactions": {
        "label": "Warehouse Transactions",
        "date_field": "createdAt",
        "status_choices": ["Created", "Verified", "Finished", "Void"],
        "fetch": lambda search, status: warehouse_transactions_repo.list_transactions(
            search=search, direction=None, status=status, limit=None
        ),
        "columns": [
            ("ID", "id"), ("Direction", "direction"), ("Reason", "reason"),
            ("PO #", "poNumber"), ("SI #", "siNumber"), ("DR #", "drNumber"),
            ("Branch", "branch"), ("Status", "status"), ("Date", "createdAt"),
        ],
    },
}


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row_date(row, date_field):
    value = row.get(date_field)
    if isinstance(value, datetime):
        return value.date()
    return value


def build_csv(dataset_key, search, status, date_from, date_to):
    dataset = DATASETS.get(dataset_key)
    if dataset is None:
        abort(404)

    rows = dataset["fetch"](search, status)

    if date_from or date_to:
        filtered = []
        for row in rows:
            row_date = _row_date(row, dataset["date_field"])
            if row_date is None:
                continue
            if date_from and row_date < date_from:
                continue
            if date_to and row_date > date_to:
                continue
            filtered.append(row)
        rows = filtered

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for header, _ in dataset["columns"]])
    for row in rows:
        writer.writerow([_cell(row.get(key)) for _, key in dataset["columns"]])

    filename = f"{dataset_key}_{date.today().isoformat()}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
