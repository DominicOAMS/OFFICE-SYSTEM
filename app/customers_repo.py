from .db import get_cursor


def list_active_customers():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.*, COUNT(cp.id) AS productCount
            FROM tbl_customers c
            LEFT JOIN tbl_customers_products cp ON cp.customerId = c.id AND cp.isDeleted = 0
            WHERE c.isDeleted = 0
            GROUP BY c.id
            ORDER BY c.name ASC, c.id ASC
            """
        )
        return cur.fetchall()


def get_customer(customer_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_customers WHERE id = %s LIMIT 1", (customer_id,))
        return cur.fetchone()


def find_active_by_code(code):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM tbl_customers WHERE code = %s AND isDeleted = 0 LIMIT 1",
            (code,),
        )
        return cur.fetchone()


def list_distinct_customer_types():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT customerType FROM tbl_customers
            WHERE isDeleted = 0 AND customerType IS NOT NULL AND customerType <> ''
            ORDER BY customerType ASC
            """
        )
        return [row["customerType"] for row in cur.fetchall()]


def list_distinct_sales_reps():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT salesRep FROM tbl_customers
            WHERE isDeleted = 0 AND salesRep IS NOT NULL AND salesRep <> ''
            ORDER BY salesRep ASC
            """
        )
        return [row["salesRep"] for row in cur.fetchall()]


def create_customer(data, created_by):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO tbl_customers
                (code, name, address, tin, paymentTermDays, salesRep, customerType,
                 isDeleted, createdBy, createdAt, updatedBy, updatedAt)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s,
                 0, %s, NOW(), %s, NOW())
            """,
            (
                data["code"],
                data["name"],
                data["address"],
                data["tin"],
                data["paymentTermDays"],
                data["salesRep"],
                data["customerType"],
                created_by,
                created_by,
            ),
        )
        return cur.lastrowid


def update_customer(customer_id, data, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_customers
            SET code = %s, name = %s, address = %s, tin = %s, paymentTermDays = %s,
                salesRep = %s, customerType = %s,
                updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (
                data["code"],
                data["name"],
                data["address"],
                data["tin"],
                data["paymentTermDays"],
                data["salesRep"],
                data["customerType"],
                updated_by,
                customer_id,
            ),
        )


def next_customer_id_number():
    """Global counter matching the legacy generator: highest existing 3rd
    hyphen-segment across all customer codes, plus one (e.g. "GLL-2026-120"
    -> 120). Codes that don't follow that [Type][Area]-[Year]-[Number]
    shape (legacy bare-numeric codes like "52") are simply skipped."""
    with get_cursor() as cur:
        cur.execute("SELECT code FROM tbl_customers WHERE isDeleted = 0")
        rows = cur.fetchall()

    highest = 0
    for row in rows:
        parts = (row["code"] or "").split("-")
        if len(parts) > 2 and parts[2].isdigit():
            highest = max(highest, int(parts[2]))
    return highest + 1


def soft_delete_customer(customer_id, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_customers
            SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (updated_by, customer_id),
        )


def list_products_for_customer(customer_id):
    """Current price per (catalog, priceCode, unit): the most recent row whose
    effectiveDate has already arrived (highest id breaks ties between rows
    sharing the same date, e.g. exact historical duplicates). Every prior price
    stays in the table as read-only history and simply stops being "the" row
    shown here once a newer one takes effect — matching the legacy system's
    price-history model."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT cp.*,
                (SELECT COUNT(*) FROM tbl_customers_products h
                 WHERE h.customerId = cp.customerId
                    AND h.catalog <=> cp.catalog
                    AND h.priceCode <=> cp.priceCode
                    AND h.unit <=> cp.unit
                    AND h.isDeleted = 0) AS versionCount
            FROM tbl_customers_products cp
            WHERE cp.customerId = %s AND cp.isDeleted = 0
                AND (cp.effectiveDate IS NULL OR cp.effectiveDate <= CURDATE())
                AND NOT EXISTS (
                    SELECT 1 FROM tbl_customers_products cp2
                    WHERE cp2.customerId = cp.customerId
                        AND cp2.catalog = cp.catalog
                        AND cp2.priceCode <=> cp.priceCode
                        AND cp2.unit <=> cp.unit
                        AND cp2.isDeleted = 0
                        AND (cp2.effectiveDate IS NULL OR cp2.effectiveDate <= CURDATE())
                        AND (
                            COALESCE(cp2.effectiveDate, '1900-01-01') > COALESCE(cp.effectiveDate, '1900-01-01')
                            OR (
                                COALESCE(cp2.effectiveDate, '1900-01-01') = COALESCE(cp.effectiveDate, '1900-01-01')
                                AND cp2.id > cp.id
                            )
                        )
                )
            ORDER BY cp.id DESC
            """,
            (customer_id,),
        )
        return cur.fetchall()


def list_price_history(customer_id, catalog, price_code, unit):
    """Every price ever recorded for one catalog line, newest first."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT cp.*, u.name AS createdByName
            FROM tbl_customers_products cp
            LEFT JOIN tbl_users u ON u.id = cp.createdBy
            WHERE cp.customerId = %s AND cp.isDeleted = 0
                AND cp.catalog <=> %s AND cp.priceCode <=> %s AND cp.unit <=> %s
            ORDER BY COALESCE(cp.effectiveDate, '1900-01-01') DESC, cp.id DESC
            """,
            (customer_id, catalog, price_code, unit),
        )
        return cur.fetchall()


def catalog_priced_under_code(customer_id, catalog, price_code):
    """Whether this catalog already has any active price under this price
    code — used to block adding it again as a "new" product, since a second
    price for an existing catalog+priceCode should go through "Add new
    price" on that row instead (keeps the old price as history)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM tbl_customers_products
            WHERE customerId = %s AND isDeleted = 0
                AND catalog = %s AND priceCode <=> %s
            LIMIT 1
            """,
            (customer_id, catalog, price_code),
        )
        return cur.fetchone() is not None


def product_price_exists(customer_id, data):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM tbl_customers_products
            WHERE customerId = %s AND isDeleted = 0
                AND catalog <=> %s AND priceCode <=> %s AND unit <=> %s
                AND category <=> %s AND price <=> %s AND effectiveDate <=> %s
            LIMIT 1
            """,
            (
                customer_id,
                data["catalog"],
                data["priceCode"],
                data["unit"],
                data["category"],
                data["price"],
                data["effectiveDate"],
            ),
        )
        return cur.fetchone() is not None


def list_price_codes_for_customer(customer_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT priceCode FROM tbl_customers_products
            WHERE customerId = %s AND isDeleted = 0 AND priceCode IS NOT NULL AND priceCode <> ''
            ORDER BY priceCode ASC
            """,
            (customer_id,),
        )
        return [row["priceCode"] for row in cur.fetchall()]


def list_active_inventory_items():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT catalog, description, category, groupType, baseUnit, salesUnit, purchaseUnit, packSize
            FROM tbl_inventory_items
            WHERE isDeleted = 0 AND status = 'AC'
            ORDER BY catalog ASC
            """
        )
        return cur.fetchall()


def list_allowed_units():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT unit FROM tbl_customers_products WHERE isDeleted = 0 AND unit IS NOT NULL AND unit <> ''
            UNION
            SELECT baseUnit FROM tbl_inventory_items WHERE isDeleted = 0 AND baseUnit IS NOT NULL AND baseUnit <> ''
            UNION
            SELECT salesUnit FROM tbl_inventory_items WHERE isDeleted = 0 AND salesUnit IS NOT NULL AND salesUnit <> ''
            UNION
            SELECT purchaseUnit FROM tbl_inventory_items WHERE isDeleted = 0 AND purchaseUnit IS NOT NULL AND purchaseUnit <> ''
            ORDER BY unit ASC
            """
        )
        return [row["unit"] for row in cur.fetchall()]


def create_product(customer_id, data, created_by):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO tbl_customers_products
                (customerId, priceCode, catalog, customerDescription, category, unit, price,
                 effectiveDate, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s,
                 %s, 0, %s, NOW(), %s, NOW())
            """,
            (
                customer_id,
                data["priceCode"],
                data["catalog"],
                data["customerDescription"],
                data["category"],
                data["unit"],
                data["price"],
                data["effectiveDate"],
                created_by,
                created_by,
            ),
        )
        return cur.lastrowid


def soft_delete_product(product_id, updated_by):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE tbl_customers_products
            SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
            WHERE id = %s
            """,
            (updated_by, product_id),
        )
