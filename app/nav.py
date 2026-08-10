NAV_ITEMS = [
    {"label": "Dashboard", "icon": "fa-tachometer-alt", "endpoint": "main.dashboard"},
    {"label": "Purchase Request", "icon": "fa-list-alt", "slug": "purchase_request"},
    {
        "label": "Purchase Order",
        "icon": "fa-cart-arrow-down",
        "children": [
            {"label": "Orders", "icon": "fa-edit", "slug": "purchase_order_orders"},
            {"label": "Fuel PO", "icon": "fa-edit", "slug": "purchase_order_fuel"},
        ],
    },
    {
        "label": "Warehouse",
        "icon": "fa-briefcase",
        "children": [
            {"label": "Stocks", "icon": "fa-boxes", "slug": "warehouse_stocks"},
            {"label": "Transactions", "icon": "fa-handshake", "slug": "warehouse_transactions"},
        ],
    },
    {"label": "Invoices", "icon": "fa-file-alt", "slug": "invoice_invoices"},
    {
        "label": "Delivery",
        "icon": "fa-truck",
        "children": [
            {"label": "Schedules", "icon": "fa-calendar", "slug": "delivery_schedules"},
            {"label": "Gatepass", "icon": "fa-door-open", "slug": "delivery_gatepass"},
            {"label": "Delivery Receipt", "icon": "fa-list-alt", "slug": "delivery_receipt"},
        ],
    },
    {
        "label": "Payables",
        "icon": "fa-clipboard-check",
        "children": [
            {"label": "PO Payables", "icon": "fa-list-alt", "slug": "payables_po"},
            {"label": "Non-PO Payables", "icon": "fa-list-alt", "slug": "payables_non_po"},
            {"label": "Check Vouchers", "icon": "fa-edit", "slug": "payables_vouchers"},
        ],
    },
    {
        "label": "Receivables",
        "icon": "fa-layer-group",
        "children": [
            {"label": "Collectibles", "icon": "fa-file-invoice-dollar", "slug": "receivables_collectibles"},
            {"label": "Collections", "icon": "fa-list-alt", "slug": "receivables_collections"},
            {"label": "Statement of Account", "icon": "fa-list-alt", "slug": "receivables_soa"},
        ],
    },
    {"label": "Reports", "icon": "fa-clone", "slug": "reports_downloadables"},
    {
        "label": "Consignment",
        "icon": "fa-id-badge",
        "children": [
            {"label": "Purchase Orders", "icon": "fa-boxes", "slug": "consignment_po"},
            {"label": "Transactions", "icon": "fa-handshake", "slug": "consignment_transactions"},
            {"label": "Snapshots", "icon": "fa-handshake", "slug": "consignment_snapshots"},
        ],
    },
    {
        "label": "Parameters",
        "icon": "fa-wrench",
        "children": [
            {"label": "Customers & Suppliers", "icon": "fa-address-book", "slug": "parameters_business_partners"},
            {"label": "Users", "icon": "fa-dot-circle", "slug": "parameters_users"},
            {"label": "Inventory Items", "icon": "fa-dot-circle", "slug": "parameters_inventory_items"},
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
