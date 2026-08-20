from .db import get_connection


def list_prices():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tbl_fuel_prices ORDER BY FIELD(fuelCategory, 'Diesel', 'Unleaded', 'Premium')"
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_price(fuel_category):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tbl_fuel_prices WHERE fuelCategory = %s LIMIT 1", (fuel_category,))
            return cur.fetchone()
    finally:
        conn.close()


def update_price(fuel_category, price_per_liter, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_fuel_prices SET pricePerLiter = %s, updatedBy = %s, updatedAt = NOW() WHERE fuelCategory = %s",
                (price_per_liter, updated_by, fuel_category),
            )
    finally:
        conn.close()
