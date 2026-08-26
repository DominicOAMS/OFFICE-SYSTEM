NAV_ITEMS = [
    {"label": "Dashboard", "icon": "layout-dashboard", "endpoint": "main.dashboard"},
    {"label": "Purchase Request", "icon": "clipboard-list", "slug": "purchase_request"},
    {
        "label": "Purchase Order",
        "icon": "shopping-cart",
        "children": [
            {"label": "Orders", "icon": "file-text", "slug": "purchase_order_orders"},
            {"label": "Fuel PO", "icon": "fuel", "slug": "purchase_order_fuel"},
        ],
    },
    {
        "label": "Warehouse",
        "icon": "warehouse",
        "children": [
            {"label": "Inventory", "icon": "boxes", "slug": "warehouse_stocks"},
            {"label": "Transactions", "icon": "arrow-left-right", "slug": "warehouse_transactions"},
        ],
    },
    {"label": "Invoices", "icon": "file-text", "slug": "invoice_invoices"},
    {
        "label": "Delivery",
        "icon": "truck",
        "children": [
            {"label": "Schedules", "icon": "calendar-days", "slug": "delivery_schedules"},
            {"label": "Gatepass", "icon": "door-open", "slug": "delivery_gatepass"},
            {"label": "Delivery Receipt", "icon": "receipt", "slug": "delivery_receipt"},
        ],
    },
    {
        "label": "Payables",
        "icon": "credit-card",
        "children": [
            {"label": "PO Payables", "icon": "file-check", "slug": "payables_po"},
            {"label": "Non-PO Payables", "icon": "file-minus", "slug": "payables_non_po"},
            {"label": "Check Vouchers", "icon": "banknote", "slug": "payables_vouchers"},
        ],
    },
    {
        "label": "Receivables",
        "icon": "layers",
        "children": [
            {"label": "Collectibles", "icon": "hand-coins", "slug": "receivables_collectibles"},
            {"label": "Collections", "icon": "wallet", "slug": "receivables_collections"},
            {"label": "Statement of Account", "icon": "file-spreadsheet", "slug": "receivables_soa"},
        ],
    },
    {"label": "Reports", "icon": "bar-chart-3", "slug": "reports_downloadables"},
    {
        "label": "Consignment",
        "icon": "package",
        "children": [
            {"label": "Purchase Orders", "icon": "package-plus", "slug": "consignment_po"},
            {"label": "Transactions", "icon": "arrow-left-right", "slug": "consignment_transactions"},
            {"label": "Snapshots", "icon": "camera", "slug": "consignment_snapshots"},
        ],
    },
    {
        "label": "Parameters",
        "icon": "settings",
        "children": [
            {"label": "Customers", "icon": "contact", "slug": "parameters_customers"},
            {"label": "Suppliers", "icon": "truck", "slug": "parameters_suppliers"},
            {"label": "Users", "icon": "users", "slug": "parameters_users"},
            {"label": "Vehicles", "icon": "car", "slug": "parameters_vehicles"},
            {"label": "Fuel Approvers", "icon": "shield-check", "slug": "parameters_fuel_approvers"},
            {"label": "Fuel Prices", "icon": "gauge", "slug": "parameters_fuel_prices"},
            {"label": "PO Approvers", "icon": "shield-check", "slug": "parameters_purchase_order_approvers"},
        ],
    },
]


def flatten_slugs():
    slugs = {}
    for item in NAV_ITEMS:
        if "slug" in item:
            slugs[item["slug"]] = item
        for child in item.get("children", []):
            slugs[child["slug"]] = child
    return slugs
