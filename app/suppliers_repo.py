from .db import get_connection


def list_active_suppliers():
    """Only suppliers with status 'Active'. Inactive ones stay in the table (and
    keep their price history) but are deliberately not listed — set a supplier
    back to Active in the database to bring it back into this list."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.*, COUNT(sp.id) AS productCount
                FROM tbl_suppliers s
                LEFT JOIN tbl_suppliers_products sp ON sp.supplierId = s.id AND sp.isDeleted = 0
                WHERE s.isDeleted = 0 AND s.status = 'Active'
                GROUP BY s.id
                ORDER BY s.name ASC, s.id ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_supplier(supplier_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tbl_suppliers WHERE id = %s LIMIT 1", (supplier_id,))
            return cur.fetchone()
    finally:
        conn.close()


def find_active_by_code(code):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tbl_suppliers WHERE code = %s AND isDeleted = 0 LIMIT 1",
                (code,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _distinct(column):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT {col} AS v FROM tbl_suppliers
                WHERE isDeleted = 0 AND {col} IS NOT NULL AND {col} <> ''
                ORDER BY {col} ASC
                """.format(col=column)
            )
            return [row["v"] for row in cur.fetchall()]
    finally:
        conn.close()


def list_distinct_categories():
    return _distinct("category")


def list_distinct_price_types():
    return _distinct("priceType")


def list_distinct_payment_terms():
    return _distinct("paymentTerm")


def create_supplier(data, created_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_suppliers
                    (code, name, category, status, address, telephoneNumber, faxNumber, email,
                     paymentTerm, tin, priceType,
                     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     0, %s, NOW(), %s, NOW())
                """,
                (
                    data["code"],
                    data["name"],
                    data["category"],
                    data["status"],
                    data["address"],
                    data["telephoneNumber"],
                    data["faxNumber"],
                    data["email"],
                    data["paymentTerm"],
                    data["tin"],
                    data["priceType"],
                    created_by,
                    created_by,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_supplier(supplier_id, data, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_suppliers
                SET code = %s, name = %s, category = %s, status = %s, address = %s,
                    telephoneNumber = %s, faxNumber = %s, email = %s,
                    paymentTerm = %s, tin = %s, priceType = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (
                    data["code"],
                    data["name"],
                    data["category"],
                    data["status"],
                    data["address"],
                    data["telephoneNumber"],
                    data["faxNumber"],
                    data["email"],
                    data["paymentTerm"],
                    data["tin"],
                    data["priceType"],
                    updated_by,
                    supplier_id,
                ),
            )
    finally:
        conn.close()


def soft_delete_supplier(supplier_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_suppliers
                SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (updated_by, supplier_id),
            )
    finally:
        conn.close()


# Rows that are the *current* price for their (catalog, priceCode, unit) line:
# the newest one whose effectiveDate has arrived, with the highest id breaking
# ties. Superseded rows stay in the table as history (see list_price_history).
_CURRENT_PRICE_WHERE = """
    sp.supplierId = %s AND sp.isDeleted = 0
    AND (sp.effectiveDate IS NULL OR sp.effectiveDate <= CURDATE())
    AND NOT EXISTS (
        SELECT 1 FROM tbl_suppliers_products sp2
        WHERE sp2.supplierId = sp.supplierId
            AND sp2.catalog <=> sp.catalog
            AND sp2.priceCode <=> sp.priceCode
            AND sp2.unit <=> sp.unit
            AND sp2.isDeleted = 0
            AND (sp2.effectiveDate IS NULL OR sp2.effectiveDate <= CURDATE())
            AND (
                COALESCE(sp2.effectiveDate, '1900-01-01') > COALESCE(sp.effectiveDate, '1900-01-01')
                OR (
                    COALESCE(sp2.effectiveDate, '1900-01-01') = COALESCE(sp.effectiveDate, '1900-01-01')
                    AND sp2.id > sp.id
                )
            )
    )
"""

_SEARCH_WHERE = """
    AND (sp.catalog LIKE %s OR sp.description LIKE %s OR sp.priceCode LIKE %s)
"""

_PRICE_CODE_WHERE = " AND sp.priceCode <=> %s"


def _filter_clauses(search, price_code, has_price_code):
    """Shared WHERE tail + params for the list/count queries. `has_price_code`
    distinguishes "no price code chosen" (show everything) from an explicitly
    blank code, which legitimately matches the rows that have none."""
    sql = ""
    params = []
    if has_price_code:
        sql += _PRICE_CODE_WHERE
        params.append(price_code or None)
    if search:
        sql += _SEARCH_WHERE
        like = "%" + search + "%"
        params += [like, like, like]
    return sql, params


def count_products_for_supplier(supplier_id, search=None, price_code=None, has_price_code=False):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n FROM tbl_suppliers_products sp WHERE " + _CURRENT_PRICE_WHERE
            params = [supplier_id]
            extra_sql, extra_params = _filter_clauses(search, price_code, has_price_code)
            sql += extra_sql
            params += extra_params
            cur.execute(sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_priced_catalogs(supplier_id, price_code):
    """Catalogs this supplier already has a live price for under one price code.
    Used to keep already-priced products out of the Add Product catalog picker —
    computed server-side because the table is paginated, so the browser only
    ever holds one page of rows."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT catalog FROM tbl_suppliers_products
                WHERE supplierId = %s AND isDeleted = 0
                    AND priceCode <=> %s
                    AND catalog IS NOT NULL AND catalog <> ''
                """,
                (supplier_id, price_code or None),
            )
            return [row["catalog"] for row in cur.fetchall()]
    finally:
        conn.close()


def list_products_for_supplier(supplier_id, search=None, limit=None, offset=0,
                               price_code=None, has_price_code=False):
    """Current prices for a supplier, newest-effective first within each catalog.
    Paginated because a single supplier can carry well over a thousand lines."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # versionCount counts DISTINCT (price, effectiveDate) pairs so the badge
            # matches what list_price_history() actually shows — exact duplicate
            # legacy rows must not inflate it. CONCAT_WS keeps NULL prices/dates
            # countable, which COUNT(DISTINCT a, b) would otherwise skip.
            sql = """
                SELECT sp.*,
                    (SELECT COUNT(DISTINCT CONCAT_WS('|',
                                COALESCE(CAST(h.price AS CHAR), '~'),
                                COALESCE(CAST(h.effectiveDate AS CHAR), '~')))
                     FROM tbl_suppliers_products h
                     WHERE h.supplierId = sp.supplierId
                        AND h.catalog <=> sp.catalog
                        AND h.priceCode <=> sp.priceCode
                        AND h.unit <=> sp.unit
                        AND h.isDeleted = 0) AS versionCount
                FROM tbl_suppliers_products sp
                WHERE
            """ + _CURRENT_PRICE_WHERE
            params = [supplier_id]
            extra_sql, extra_params = _filter_clauses(search, price_code, has_price_code)
            sql += extra_sql
            params += extra_params

            sql += " ORDER BY sp.catalog ASC, sp.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params += [int(limit), int(offset)]

            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def list_price_history(supplier_id, catalog, price_code, unit):
    """Every distinct price ever recorded for one catalog line, newest first.

    Grouped by (price, effectiveDate) because the legacy data contains exact
    duplicate rows — the same price on the same date imported more than once —
    which otherwise showed up as repeated identical history entries. Only truly
    identical rows collapse; two different prices on the same date remain
    separate entries."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    MIN(sp.id)          AS id,
                    sp.price            AS price,
                    sp.effectiveDate    AS effectiveDate,
                    MIN(sp.createdAt)   AS createdAt,
                    COUNT(*)            AS duplicateCount,
                    MIN(u.name)         AS createdByName
                FROM tbl_suppliers_products sp
                LEFT JOIN tbl_users u ON u.id = sp.createdBy
                WHERE sp.supplierId = %s AND sp.isDeleted = 0
                    AND sp.catalog <=> %s AND sp.priceCode <=> %s AND sp.unit <=> %s
                GROUP BY sp.price, sp.effectiveDate
                ORDER BY COALESCE(sp.effectiveDate, '1900-01-01') DESC, MIN(sp.id) DESC
                """,
                (supplier_id, catalog, price_code, unit),
            )
            return cur.fetchall()
    finally:
        conn.close()


def product_price_exists(supplier_id, data, exclude_id=None):
    """exclude_id skips the row being edited, so re-saving an unchanged row
    doesn't trip the duplicate guard against itself."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT 1 FROM tbl_suppliers_products
                WHERE supplierId = %s AND isDeleted = 0
                    AND catalog <=> %s AND priceCode <=> %s AND unit <=> %s
                    AND price <=> %s AND effectiveDate <=> %s
            """
            params = [
                supplier_id,
                data["catalog"],
                data["priceCode"],
                data["unit"],
                data["price"],
                data["effectiveDate"],
            ]
            if exclude_id is not None:
                sql += " AND id <> %s"
                params.append(exclude_id)
            sql += " LIMIT 1"
            cur.execute(sql, params)
            return cur.fetchone() is not None
    finally:
        conn.close()


def get_product(product_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tbl_suppliers_products WHERE id = %s LIMIT 1", (product_id,))
            return cur.fetchone()
    finally:
        conn.close()


def list_price_codes_for_supplier(supplier_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT priceCode FROM tbl_suppliers_products
                WHERE supplierId = %s AND isDeleted = 0 AND priceCode IS NOT NULL AND priceCode <> ''
                ORDER BY priceCode ASC
                """,
                (supplier_id,),
            )
            return [row["priceCode"] for row in cur.fetchall()]
    finally:
        conn.close()


def list_catalog_suggestions(supplier_id):
    """Catalogs this supplier already quotes, plus the inventory master list.
    Scoped to one supplier rather than all of them: the full cross-supplier list
    is ~2,250 entries and mostly irrelevant when pricing a single supplier.
    It stays a suggestion list, not a closed set — only 408 of 2,202 distinct
    supplier catalogs exist in tbl_inventory_items, so free text is allowed."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT catalog, MAX(description) AS description, MAX(category) AS category FROM (
                    SELECT catalog, description, category FROM tbl_suppliers_products
                    WHERE isDeleted = 0 AND supplierId = %s AND catalog IS NOT NULL AND catalog <> ''
                    UNION ALL
                    SELECT catalog, description, category FROM tbl_inventory_items
                    WHERE isDeleted = 0 AND catalog IS NOT NULL AND catalog <> ''
                ) t
                GROUP BY catalog
                ORDER BY catalog ASC
                """,
                (supplier_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def list_allowed_units():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT unit FROM tbl_suppliers_products WHERE isDeleted = 0 AND unit IS NOT NULL AND unit <> ''
                UNION
                SELECT baseUnit FROM tbl_inventory_items WHERE isDeleted = 0 AND baseUnit IS NOT NULL AND baseUnit <> ''
                UNION
                SELECT purchaseUnit FROM tbl_inventory_items WHERE isDeleted = 0 AND purchaseUnit IS NOT NULL AND purchaseUnit <> ''
                ORDER BY unit ASC
                """
            )
            return [row["unit"] for row in cur.fetchall()]
    finally:
        conn.close()


def create_product(supplier_id, data, created_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_suppliers_products
                    (supplierId, catalog, description, category, unit, price, priceCode, effectiveDate,
                     isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                     0, %s, NOW(), %s, NOW())
                """,
                (
                    supplier_id,
                    data["catalog"],
                    data["description"],
                    data["category"],
                    data["unit"],
                    data["price"],
                    data["priceCode"],
                    data["effectiveDate"],
                    created_by,
                    created_by,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_product(product_id, data, updated_by):
    """Corrects a price row in place. This is deliberately different from adding
    a newer price: use create_product() when the supplier actually changes their
    price (that keeps the old one as history), and this only to fix a mistake."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_suppliers_products
                SET catalog = %s, description = %s, category = %s, unit = %s,
                    price = %s, priceCode = %s, effectiveDate = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (
                    data["catalog"],
                    data["description"],
                    data["category"],
                    data["unit"],
                    data["price"],
                    data["priceCode"],
                    data["effectiveDate"],
                    updated_by,
                    product_id,
                ),
            )
    finally:
        conn.close()


def soft_delete_product(product_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_suppliers_products
                SET isDeleted = 1, updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (updated_by, product_id),
            )
    finally:
        conn.close()
