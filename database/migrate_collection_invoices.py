"""One-time migration: parses tbl_collection's legacy comma-separated Invoices text field
(e.g. "209765,209628,209630") into real tbl_collection_invoices junction rows, then cascades
every matched invoice that isn't already Paid/Void to Paid - see migrate_collections.sql's
header comment and the approved plan for why this lives in Python rather than pure SQL
(MySQL 5.7 has no clean way to split a variable-length comma list into rows) and why the
invoice-status cascade is a deliberate, explicitly-flagged exception to "migrations don't
touch already-migrated data" (confirmed 584 real historical collections would otherwise look
uncollected on the new Collectibles report).

Must run AFTER migrate_collections.sql. Idempotent: re-running is safe (junction rows use
INSERT IGNORE against the table's UNIQUE(collectionId, invoiceId), and the invoice cascade
only ever touches rows still NOT IN ('Paid', 'Void')).
"""
import sys

sys.path.insert(0, r"C:\Users\OAMS Fred\Downloads\NEW OFFICE SYSTEM DOM\OFFICE-SYSTEM")

from app.db import get_connection


def normalize(ref):
    """Legacy invoice-number references are inconsistently zero-padded and
    tbl_invoices.invoiceNumber itself isn't uniformly padded either (4-10 chars) - comparing
    by integer value is the only reliable normalization. Non-numeric refs (there are none
    expected, but defensively) return None rather than raising."""
    ref = ref.strip()
    if not ref.isdigit():
        return None
    return int(ref)


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id AS collectionId, c.dateCollected, legacy.Invoices "
                "FROM db_os_2026.tbl_collections c "
                "JOIN db_oams_app_2026.tbl_collection legacy ON legacy.ORNumber = c.orNumber "
                "WHERE legacy.Invoices IS NOT NULL AND legacy.Invoices != ''"
            )
            collections = cur.fetchall()
            print(f"{len(collections)} collections have an Invoices reference to parse")

            cur.execute("SELECT id, invoiceNumber FROM tbl_invoices")
            by_numeric = {}
            for row in cur.fetchall():
                n = normalize(row["invoiceNumber"])
                if n is not None:
                    by_numeric[n] = row["id"]
            print(f"{len(by_numeric)} invoices have a numeric invoiceNumber to match against")

            junction_rows = []
            invoice_ids_to_cascade = {}  # invoiceId -> earliest dateCollected among matches
            unmatched_refs = 0
            total_refs = 0

            for c in collections:
                seen_this_collection = set()
                for raw_ref in c["Invoices"].split(","):
                    raw_ref = raw_ref.strip()
                    if not raw_ref:
                        continue
                    total_refs += 1
                    n = normalize(raw_ref)
                    invoice_id = by_numeric.get(n) if n is not None else None
                    if invoice_id is None:
                        unmatched_refs += 1
                        continue
                    if invoice_id in seen_this_collection:
                        continue
                    seen_this_collection.add(invoice_id)
                    junction_rows.append((c["collectionId"], invoice_id))
                    existing = invoice_ids_to_cascade.get(invoice_id)
                    if existing is None or (c["dateCollected"] and c["dateCollected"] < existing):
                        invoice_ids_to_cascade[invoice_id] = c["dateCollected"]

            print(f"{total_refs} total references, {unmatched_refs} unmatched, "
                  f"{len(junction_rows)} junction rows to insert, "
                  f"{len(invoice_ids_to_cascade)} distinct invoices to consider for the Paid cascade")

            cur.executemany(
                "INSERT IGNORE INTO tbl_collection_invoices (collectionId, invoiceId) VALUES (%s, %s)",
                junction_rows,
            )
            print(f"junction insert: {cur.rowcount} rows actually inserted (IGNORE skips reruns)")

            cascaded = 0
            for invoice_id, date_collected in invoice_ids_to_cascade.items():
                cur.execute(
                    """
                    UPDATE tbl_invoices
                    SET status = 'Paid', paidAt = %s, updatedAt = NOW()
                    WHERE id = %s AND status NOT IN ('Paid', 'Void')
                    """,
                    (date_collected, invoice_id),
                )
                cascaded += cur.rowcount

            print(f"invoice cascade: {cascaded} invoices flipped to Paid")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
