from .db import get_cursor


def list_prices():
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM tbl_fuel_prices ORDER BY FIELD(fuelCategory, 'Diesel', 'Unleaded', 'Premium')"
        )
        return cur.fetchall()


def get_price(fuel_category):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tbl_fuel_prices WHERE fuelCategory = %s LIMIT 1", (fuel_category,))
        return cur.fetchone()


def update_price(fuel_category, price_per_liter, updated_by):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tbl_fuel_prices SET pricePerLiter = %s, updatedBy = %s, updatedAt = NOW() WHERE fuelCategory = %s",
            (price_per_liter, updated_by, fuel_category),
        )
