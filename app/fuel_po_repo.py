from .db import get_connection

_FUEL_PO_COLUMNS = """
    fp.*,
    reqFor.name AS requestedForName,
    reqBy.name AS requestedByName,
    v.plateNumber, v.vehicleModel,
    appr.name AS approverName,
    finalAppr.name AS finalApproverName
"""

_FUEL_PO_FROM = """
    FROM tbl_fuel_pos fp
    LEFT JOIN tbl_users reqFor ON reqFor.id = fp.requestedForUserId
    LEFT JOIN tbl_users reqBy ON reqBy.id = fp.requestedByUserId
    LEFT JOIN tbl_vehicles v ON v.id = fp.vehicleId
    LEFT JOIN tbl_users appr ON appr.id = fp.approverUserId
    LEFT JOIN tbl_users finalAppr ON finalAppr.id = fp.finalApproverUserId
"""


def _filter_clauses(search, status):
    sql = " WHERE fp.isDeleted = 0"
    params = []
    if status:
        sql += " AND fp.status = %s"
        params.append(status)
    if search:
        # The per-trip EXISTS matters: fp.destination is a single VARCHAR(255) rollup of
        # every trip's itinerary, so on a multi-date PO the tail gets clipped and those
        # stops would silently stop being findable. Each trip's own summary is far shorter.
        sql += """ AND (
            reqFor.name LIKE %s OR reqBy.name LIKE %s OR v.plateNumber LIKE %s
            OR fp.destination LIKE %s OR fp.purpose LIKE %s OR CAST(fp.id AS CHAR) LIKE %s
            OR EXISTS (
                SELECT 1 FROM tbl_fuel_po_trips t
                WHERE t.fuelPoId = fp.id AND t.destination LIKE %s
            )
        )"""
        like = "%" + search + "%"
        params += [like, like, like, like, like, like, like]
    return sql, params


def count_fuel_pos(search=None, status=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT COUNT(*) AS n" + _FUEL_PO_FROM
            extra_sql, params = _filter_clauses(search, status)
            cur.execute(sql + extra_sql, params)
            return cur.fetchone()["n"]
    finally:
        conn.close()


def list_fuel_pos(search=None, status=None, limit=None, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = "SELECT " + _FUEL_PO_COLUMNS + _FUEL_PO_FROM
            extra_sql, params = _filter_clauses(search, status)
            sql += extra_sql + " ORDER BY fp.id DESC"
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params = params + [int(limit), int(offset)]
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_fuel_po(po_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + _FUEL_PO_COLUMNS + _FUEL_PO_FROM + " WHERE fp.id = %s LIMIT 1",
                (po_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_fuel_po(data, created_by):
    """Insert the PO, its dated trips, and each trip's stops - in one transaction.

    This is the only place in the codebase that opens an explicit transaction, and the
    only place that needs one: every other repo function writes exactly one row, where
    autocommit IS the transaction. Here the PO row carries rollups (amountRequested,
    estimatedAmount, destination) computed from the trips BEFORE those trips exist as
    rows, so a failure partway through autocommit would leave a permanently wrong total -
    a PO approved for an amount whose trips were never saved, with nothing that would
    ever detect the drift.
    """
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_fuel_pos
                    (requestDate, requestedForUserId, requestedByUserId, startLocation, startLat, startLng,
                     vehicleId, fuelType, fuelEfficiencyKmPerLiter,
                     destination, destinationLat, destinationLng, estimatedDistanceKm, estimatedAmount,
                     purpose, odometer, odometerAttachmentPath, amountRequested,
                     approverUserId, status, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (CURDATE(), %s, %s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s, %s, %s,
                     %s, %s, %s, %s,
                     %s, 'Pending Approval', 0, %s, NOW(), %s, NOW())
                """,
                (
                    data["requestedForUserId"],
                    data["requestedByUserId"],
                    data["startLocation"],
                    data["startLat"],
                    data["startLng"],
                    data["vehicleId"],
                    data["fuelType"],
                    data["fuelEfficiencyKmPerLiter"],
                    data["destination"],
                    data["destinationLat"],
                    data["destinationLng"],
                    data["estimatedDistanceKm"],
                    data["estimatedAmount"],
                    data["purpose"],
                    data["odometer"],
                    data["odometerAttachmentPath"],
                    data["amountRequested"],
                    data["approverUserId"],
                    created_by,
                    created_by,
                ),
            )
            fuel_po_id = cur.lastrowid

            for trip_seq, trip in enumerate(data["trips"], start=1):
                cur.execute(
                    """
                    INSERT INTO tbl_fuel_po_trips
                        (fuelPoId, sequence, tripDate, startLocation, startLat, startLng,
                         destination, estimatedDistanceKm, estimatedAmount, amountRequested)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        fuel_po_id,
                        trip_seq,
                        trip["date"],
                        trip["startLocation"],
                        trip["startLat"],
                        trip["startLng"],
                        trip["destination"],
                        trip["estimatedDistanceKm"],
                        trip["estimatedAmount"],
                        trip["amountRequested"],
                    ),
                )
                trip_id = cur.lastrowid

                # sequence restarts at 1 within each trip
                for stop_seq, dest in enumerate(trip["destinations"], start=1):
                    cur.execute(
                        """
                        INSERT INTO tbl_fuel_po_destinations
                            (fuelPoId, tripId, sequence, destination, destinationLat, destinationLng)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (fuel_po_id, trip_id, stop_seq, dest["label"], dest["lat"], dest["lng"]),
                    )

        conn.commit()
        return fuel_po_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_trips_for_fuel_pos(po_ids):
    """Every trip (with its ordered stops attached) for a page of Fuel POs, keyed by
    fuelPoId. Always exactly two queries no matter how many POs are on the page - the
    list renders 30 at a time and must not fan out into per-row lookups.

    Returns {fuelPoId: [{<trip row>, "destinations": [<dest row>, ...]}, ...]}, trips in
    `sequence` order and each trip's stops in their own `sequence` order. A PO id with no
    trips is simply absent from the dict.
    """
    po_ids = [int(i) for i in po_ids]  # coerce BEFORE interpolating placeholders
    if not po_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(po_ids))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM tbl_fuel_po_trips
                WHERE fuelPoId IN ({placeholders})
                ORDER BY fuelPoId ASC, sequence ASC
                """,
                po_ids,
            )
            trips = cur.fetchall()

            # Filtered on the destinations table's own fuelPoId rather than joined through
            # trips - that denormalized column is exactly why it was kept.
            cur.execute(
                f"""
                SELECT * FROM tbl_fuel_po_destinations
                WHERE fuelPoId IN ({placeholders})
                ORDER BY tripId ASC, sequence ASC
                """,
                po_ids,
            )
            destinations = cur.fetchall()
    finally:
        conn.close()

    stops_by_trip = {}
    for dest in destinations:
        stops_by_trip.setdefault(dest["tripId"], []).append(dest)

    trips_by_po = {}
    for trip in trips:
        trip["destinations"] = stops_by_trip.get(trip["id"], [])
        trips_by_po.setdefault(trip["fuelPoId"], []).append(trip)
    return trips_by_po


def get_trips_for_fuel_po(po_id):
    """One PO's trips - thin wrapper so single-record callers don't build a list."""
    return list_trips_for_fuel_pos([po_id]).get(int(po_id), [])


def soft_delete_fuel_po(po_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_fuel_pos SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, po_id),
            )
    finally:
        conn.close()


def approve_stage1(po_id, approved_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_fuel_pos
                SET status = 'Pending Final Approval', approverActionAt = NOW(), approverRemarks = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (remarks, approved_by, po_id),
            )
    finally:
        conn.close()


def reject_stage1(po_id, rejected_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_fuel_pos
                SET status = 'Rejected', approverActionAt = NOW(), approverRemarks = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (remarks, rejected_by, po_id),
            )
    finally:
        conn.close()


def approve_stage2(po_id, approved_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_fuel_pos
                SET status = 'Approved', finalApproverUserId = %s, finalApproverActionAt = NOW(),
                    finalApproverRemarks = %s, updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (approved_by, remarks, approved_by, po_id),
            )
    finally:
        conn.close()


def reject_stage2(po_id, rejected_by, remarks):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_fuel_pos
                SET status = 'Rejected', finalApproverUserId = %s, finalApproverActionAt = NOW(),
                    finalApproverRemarks = %s, updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (rejected_by, remarks, rejected_by, po_id),
            )
    finally:
        conn.close()
