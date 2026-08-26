"""One-off migration: parse tbl_purchase_order_items.allocation's legacy free
text into structured tbl_purchase_order_item_allocations rows.

The legacy field held entries shaped like:
    PUL-2018-17:PAMANA MEDICAL CENTER->1
separated by "<br />" (with stray \\r around it), joined with either colon
before the customer name or an arrow before the quantity. This mirrors the
tbl_supplier_products.priceCode / NOANumber-style free-text-turned-structured
patterns already migrated elsewhere in this project.

Profiled before writing this (see conversation, not re-derived here):
  * 3,223 of 14,787 line items have a non-blank allocation.
  * 3,545 total "code:name->qty" segments across those rows; 3,520 (99.3%)
    match the shape above. The other 25 are missing a quantity after "->"
    (blank), literal "undefined", or one row (line item 5652) that's an
    entirely different format ("1st Delivery- Q4 2024" style delivery notes,
    not a customer allocation at all) - skipped, nothing to parse there.
  * Of the 3,520 parsed segments, 3,422 (97.2%) resolve to a real
    tbl_customers.code. The remaining 98 use placeholder codes ("", "na",
    "BICOL", "stocks") that were never real customers - skipped rather than
    inventing a fake customer row for them. "stocks" likely meant "kept as
    unallocated inventory," but that's a different concept from a customer
    allocation, so it's left out rather than guessed at.
  * ~10% of rows have sum(parsed allocations) != the item's own quantity
    (usually less, i.e. partially allocated with the rest going to general
    stock) - migrated as-is; the app's own validation (sum <= quantity) only
    applies going forward to newly created POs, not retroactively to this
    historical data.

The old text column is left in place as a raw-text fallback/audit trail; the
app itself no longer reads or writes it after this migration.

Idempotent and safe to re-run: skips any purchaseOrderItemId that already has
allocation rows.

Run once with the project venv: venv\\Scripts\\python.exe database\\migrate_legacy_allocations.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection

SEPARATOR = re.compile(r"\r?\n?<br\s*/?>\r?\n?|\r\n|\n")
SEGMENT = re.compile(r"^\s*(.*?)\s*:\s*(.*?)\s*->\s*(-?\d+(?:\.\d+)?)\s*$")


def main():
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id, i.allocation
                FROM tbl_purchase_order_items i
                LEFT JOIN tbl_purchase_order_item_allocations a ON a.purchaseOrderItemId = i.id
                WHERE i.allocation IS NOT NULL AND i.allocation <> '' AND a.id IS NULL
                GROUP BY i.id, i.allocation
                """
            )
            rows = cur.fetchall()

            cur.execute("SELECT id, code FROM tbl_customers WHERE isDeleted = 0")
            code_to_id = {r["code"]: r["id"] for r in cur.fetchall()}

            print(f"{len(rows)} line item(s) with unmigrated allocation text.")

            inserted = 0
            skipped_segments = []
            unmatched_codes = {}

            for row in rows:
                for segment in SEPARATOR.split(row["allocation"]):
                    segment = segment.strip()
                    if not segment:
                        continue
                    m = SEGMENT.match(segment)
                    if not m:
                        skipped_segments.append((row["id"], segment))
                        continue
                    code = m.group(1).strip()
                    quantity = m.group(3)
                    customer_id = code_to_id.get(code)
                    if customer_id is None:
                        unmatched_codes[code] = unmatched_codes.get(code, 0) + 1
                        continue
                    cur.execute(
                        """
                        INSERT INTO tbl_purchase_order_item_allocations
                            (purchaseOrderItemId, customerId, quantity, createdAt, updatedAt)
                        SELECT %s, %s, %s, createdAt, updatedAt
                        FROM tbl_purchase_order_items WHERE id = %s
                        """,
                        (row["id"], customer_id, quantity, row["id"]),
                    )
                    inserted += 1

        conn.commit()
        print(f"Inserted {inserted} allocation row(s).")
        print(f"Skipped {len(skipped_segments)} unparseable segment(s):")
        for item_id, segment in skipped_segments[:20]:
            print(f"  item {item_id}: {segment!r}")
        if unmatched_codes:
            print(f"Skipped segments with a code that isn't a real customer ({sum(unmatched_codes.values())} total):")
            for code, count in sorted(unmatched_codes.items()):
                print(f"  {code!r}: {count}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
