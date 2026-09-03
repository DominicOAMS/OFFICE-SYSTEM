from .db import get_cursor


def list_all_items():
    """Every non-deleted catalog item, unpaginated - same "master data, client-filtered"
    shape as customers_repo.list_active_customers(). This is the base list the merged
    Inventory page renders; on-hand quantity is layered on top by
    warehouse_transactions_repo.list_stock_balances(), not stored here."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM tbl_inventory_items
            WHERE isDeleted = 0
            ORDER BY catalog ASC
            """
        )
        return cur.fetchall()


def get_item(item_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_inventory_items WHERE id = %s LIMIT 1", (item_id,))
        return cur.fetchone()


def create_item(data, created_by):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO tbl_inventory_items
                (catalog, description, category, groupType, baseUnit, salesUnit,
                 purchaseUnit, packSize, status,
                 isDeleted, createdBy, createdAt, updatedBy, updatedAt)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s,
                 0, %s, NOW(), %s, NOW())
            """,
            (
                data["catalog"],
                data["description"],
                data["category"],
                data["groupType"],
                data["baseUnit"],
                data["salesUnit"],
                data["purchaseUnit"],
                data["packSize"],
                data["status"],
                created_by,
                created_by,
            ),
        )
        return cur.lastrowid


def update_item(item_id, data, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_inventory_items
            SET catalog = %s, description = %s, category = %s, groupType = %s,
                baseUnit = %s, salesUnit = %s, purchaseUnit = %s, packSize = %s,
                status = %s, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (
                data["catalog"],
                data["description"],
                data["category"],
                data["groupType"],
                data["baseUnit"],
                data["salesUnit"],
                data["purchaseUnit"],
                data["packSize"],
                data["status"],
                updated_by,
                item_id,
            ),
        )


def soft_delete_item(item_id, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_inventory_items
            SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (updated_by, item_id),
        )
