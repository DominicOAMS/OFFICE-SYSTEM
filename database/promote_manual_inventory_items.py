"""One-off migration: promote every free-text (uncatalogued) warehouse transaction
line item into a real tbl_inventory_items catalog row, so it gets Edit/Delete on the
Inventory page like any other item instead of being permanently View-only.

Grouped by catalogCode alone (not catalogCode+description) - the same code was
routinely typed with several slightly different descriptions across transactions
(e.g. "A-HBE 52 WELLS" / "ANTI-HBE REAGENT" / "ECI A-HBE 52 WELLS (NON-US)" all under
catalogCode "8864860L"), and those are clearly the same real item, not distinct ones.
The catalog row's description/category/baseUnit are the most-frequent non-null value
in that code's group (ties broken by the longest string, then alphabetically).

Existing transaction line items are NOT rewritten - each keeps its own originally
typed description/unit/quantity forever (same "freeze what it said" reasoning as
enteredQuantity/enteredPackSize). Only `itemId` is backfilled, purely to link that
historical row to the catalog record describing the same real-world item; that's
what lets list_stock_balances()'s existing itemId-keyed aggregation merge them into
one row on the Inventory page instead of a separate View-only entry per code.

Rows with no catalogCode at all (2 legacy rows with both catalogCode and description
NULL - pre-existing migration artifacts, not real data) are left untouched; there's
nothing to identify them by.

Idempotent and safe to re-run: skips a catalogCode that already has a catalog row
(still runs the itemId backfill against it, in case a prior run was interrupted
before that step), and only ever touches wi.itemId where it's still NULL.

Run once with the project venv: venv\\Scripts\\python.exe database\\promote_manual_inventory_items.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection
from app.routes import _clip

SYSTEM_NOTE_USER = None  # createdBy left NULL - this is a system migration, not a person's action


def pick_representative(values):
    """values: iterable of (text, count). Most frequent wins; ties broken by
    longest text, then alphabetically, so the choice is fully deterministic."""
    if not values:
        return None
    return sorted(values, key=lambda tc: (-tc[1], -len(tc[0]), tc[0]))[0][0]


def main():
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT catalogCode, description, category, unit, COUNT(*) AS cnt
                FROM tbl_warehouse_transaction_items
                WHERE itemId IS NULL AND catalogCode IS NOT NULL AND catalogCode <> ''
                GROUP BY catalogCode, description, category, unit
                """
            )
            rows = cur.fetchall()

            by_code = defaultdict(lambda: {"desc": [], "cat": [], "unit": [], "total": 0})
            for r in rows:
                g = by_code[r["catalogCode"]]
                g["total"] += r["cnt"]
                if r["description"]:
                    g["desc"].append((r["description"], r["cnt"]))
                if r["category"]:
                    g["cat"].append((r["category"], r["cnt"]))
                if r["unit"]:
                    g["unit"].append((r["unit"], r["cnt"]))

            print(f"{len(by_code)} distinct catalog codes to promote (from {len(rows)} description/unit variants).")

            created = 0
            reused = 0
            linked_rows = 0

            for code, g in sorted(by_code.items()):
                # Clipped to each column's real limit - a handful of legacy free-text
                # descriptions run past 900 characters (someone typed an entire kit's
                # contents into the field), which STRICT_TRANS_TABLES rejects outright
                # rather than silently truncating.
                description = _clip(pick_representative(g["desc"]) or code, limit=255)
                category = _clip(pick_representative(g["cat"]) or "", limit=50) or None
                unit = _clip(pick_representative(g["unit"]) or "", limit=30) or None

                cur.execute("SELECT id FROM tbl_inventory_items WHERE catalog = %s", (code,))
                existing = cur.fetchone()
                if existing:
                    item_id = existing["id"]
                    reused += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO tbl_inventory_items
                            (catalog, description, category, baseUnit, status,
                             isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                        VALUES (%s, %s, %s, %s, 'AC', 0, %s, NOW(), %s, NOW())
                        """,
                        (code, description, category, unit, SYSTEM_NOTE_USER, SYSTEM_NOTE_USER),
                    )
                    item_id = cur.lastrowid
                    created += 1

                cur.execute(
                    "UPDATE tbl_warehouse_transaction_items SET itemId = %s WHERE itemId IS NULL AND catalogCode = %s",
                    (item_id, code),
                )
                linked_rows += cur.rowcount
                print(f'  {code} -> "{description}" ({g["total"]} historical line(s), {cur.rowcount} linked now)')

            cur.execute(
                """
                SELECT COUNT(*) c FROM tbl_warehouse_transaction_items
                WHERE itemId IS NULL AND (catalogCode IS NULL OR catalogCode = '')
                """
            )
            skipped = cur.fetchone()["c"]

        conn.commit()
        print()
        print(f"Done. Created {created} new catalog item(s), reused {reused} existing, linked {linked_rows} historical line item(s).")
        print(f"Skipped {skipped} line item(s) with no catalogCode at all (nothing to identify them by) - left as-is.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
