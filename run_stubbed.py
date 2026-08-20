"""Dev-only harness: runs the real app with the DB repos stubbed out.

Exists so the Fuel PO UI can be exercised in a browser while the LAN MySQL host is
unreachable. Every route, template and bit of JS is the real thing - only the repo
functions and the routing call are replaced, so this verifies the UI without touching (or
needing) the database. Submissions are captured in memory and printed, not persisted.

Not imported by the app and not part of the deployment; delete or ignore in production.
"""
import io
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from app import create_app
from app import routes as routes_mod

USERS = [
    {"id": 2, "name": "Noriel Agno"},
    {"id": 7, "name": "Eddie Magdura"},
    {"id": 8, "name": "Giliw Ibanez Jr."},
    {"id": 29, "name": "Michael Vitto"},
]

VEHICLES = [
    {
        "id": 1, "plateNumber": "STUB 001", "vehicleModel": "Toyota Vios",
        "fuelType": "UNLEADED", "fuelEfficiencyKmPerLiter": Decimal("12.00"),
        "fuelPriceCategory": "Unleaded", "assignedUserId": 2,
        "assignedUserName": "Noriel Agno", "status": "Active", "isDeleted": 0,
    },
    {
        "id": 2, "plateNumber": "STUB 002", "vehicleModel": "Hilux (no km/L set)",
        "fuelType": "DIESEL", "fuelEfficiencyKmPerLiter": None,
        "fuelPriceCategory": "Diesel", "assignedUserId": None,
        "assignedUserName": None, "status": "Active", "isDeleted": 0,
    },
]

APPROVERS = [{"id": 1, "userId": 7, "role": "Approver", "name": "Eddie Magdura", "email": "e@x"}]
FINAL_APPROVERS = [{"id": 2, "userId": 8, "role": "Final Approver", "name": "Giliw Ibanez Jr.", "email": "g@x"}]

_PO = {
    "id": 1085, "requestDate": date(2026, 8, 20),
    "requestedForUserId": 2, "requestedByUserId": 2,
    "requestedForName": "Noriel Agno", "requestedByName": "Noriel Agno",
    "legacyDriverName": None, "legacyPlateNumber": None,
    "plateNumber": "STUB 001", "vehicleModel": "Toyota Vios",
    "fuelType": "UNLEADED", "fuelEfficiencyKmPerLiter": Decimal("12.00"),
    "startLocation": "Office", "startLat": Decimal("14.2"), "startLng": Decimal("121.1"),
    "destination": "Aug 21: A -> B | Aug 22: C", "destinationLat": None, "destinationLng": None,
    "estimatedDistanceKm": Decimal("110.00"), "estimatedAmount": Decimal("550.00"),
    "purpose": "Field work", "odometer": 1000, "odometerAttachmentPath": None,
    "legacyOdometerText": None, "amountRequested": Decimal("600.00"), "legacyAmountText": None,
    "approverUserId": 7, "approverName": "Eddie Magdura", "approverActionAt": None,
    "approverRemarks": None, "finalApproverUserId": None, "finalApproverName": None,
    "finalApproverActionAt": None, "finalApproverRemarks": None,
    "status": "Pending Approval", "legacyStatus": None, "isDeleted": 0,
    "createdBy": 2, "createdAt": datetime(2026, 8, 20, 9, 0), "updatedBy": 2,
    "updatedAt": datetime(2026, 8, 20, 9, 0),
}

_TRIPS = {
    1085: [
        {
            "id": 1, "fuelPoId": 1085, "sequence": 1, "tripDate": date(2026, 8, 21),
            "startLocation": "Office, Calamba", "startLat": Decimal("14.2"), "startLng": Decimal("121.1"),
            "destination": "A -> B", "estimatedDistanceKm": Decimal("50.00"),
            "estimatedAmount": Decimal("250.00"), "amountRequested": Decimal("300.00"),
            "destinations": [
                {"id": 1, "fuelPoId": 1085, "tripId": 1, "sequence": 1, "destination": "Stop A",
                 "destinationLat": Decimal("14.5"), "destinationLng": Decimal("121.0")},
                {"id": 2, "fuelPoId": 1085, "tripId": 1, "sequence": 2, "destination": "Stop B",
                 "destinationLat": Decimal("14.6"), "destinationLng": Decimal("121.2")},
            ],
        },
        {
            "id": 2, "fuelPoId": 1085, "sequence": 2, "tripDate": date(2026, 8, 22),
            "startLocation": "Office, Calamba", "startLat": Decimal("14.2"), "startLng": Decimal("121.1"),
            "destination": "C", "estimatedDistanceKm": Decimal("60.00"),
            "estimatedAmount": Decimal("300.00"), "amountRequested": Decimal("300.00"),
            "destinations": [
                {"id": 3, "fuelPoId": 1085, "tripId": 2, "sequence": 1, "destination": "Stop C",
                 "destinationLat": Decimal("14.7"), "destinationLng": Decimal("121.3")},
            ],
        },
    ],
}


def _fake_distance(waypoints):
    """Deterministic stand-in for the routing API: ~11km per hop, no network."""
    return round(11.3 * (len(waypoints) - 1), 2)


def _capture_create(data, created_by):
    print("\n=== create_fuel_po CALLED (stub - nothing persisted) ===")
    print("  createdBy         :", created_by)
    print("  vehicleId         :", data["vehicleId"], "| approverUserId:", data["approverUserId"])
    print("  PO destination    :", data["destination"])
    print("  PO amountRequested:", data["amountRequested"])
    print("  PO estimatedAmount:", data["estimatedAmount"], "| distance:", data["estimatedDistanceKm"])
    print("  startLocation     :", data["startLocation"])
    print("  trips             :", len(data["trips"]))
    for i, t in enumerate(data["trips"], 1):
        print(f"    [{i}] {t['date']}  amount={t['amountRequested']}  est={t['estimatedAmount']}"
              f"  km={t['estimatedDistanceKm']}")
        print(f"        from: {t['startLocation']}")
        for j, d in enumerate(t["destinations"], 1):
            print(f"        stop {j}: {d['label']}  ({d['lat']}, {d['lng']})")
    print("=== end ===\n")
    return 9999


PATCHES = [
    mock.patch.object(routes_mod.fuel_po_repo, "count_fuel_pos", lambda *a, **k: 1),
    mock.patch.object(routes_mod.fuel_po_repo, "list_fuel_pos", lambda *a, **k: [dict(_PO)]),
    mock.patch.object(routes_mod.fuel_po_repo, "list_trips_for_fuel_pos", lambda ids: dict(_TRIPS)),
    mock.patch.object(routes_mod.fuel_po_repo, "create_fuel_po", _capture_create),
    mock.patch.object(routes_mod.fuel_po_repo, "get_fuel_po", lambda po_id: dict(_PO)),
    mock.patch.object(routes_mod.vehicles_repo, "list_active_vehicles", lambda: [dict(v) for v in VEHICLES]),
    mock.patch.object(
        routes_mod.vehicles_repo, "get_vehicle",
        lambda vid: next((dict(v) for v in VEHICLES if v["id"] == int(vid)), None),
    ),
    mock.patch.object(routes_mod.users_repo, "list_active_users", lambda: [dict(u) for u in USERS]),
    mock.patch.object(routes_mod.fuel_approvers_repo, "list_approvers", lambda: [dict(a) for a in APPROVERS]),
    mock.patch.object(routes_mod.fuel_approvers_repo, "list_final_approvers", lambda: [dict(a) for a in FINAL_APPROVERS]),
    mock.patch.object(routes_mod.fuel_prices_repo, "get_price",
                      lambda cat: {"fuelCategory": cat, "pricePerLiter": Decimal("58.00")}),
    mock.patch.object(routes_mod.routing, "get_route_distance_km", _fake_distance),
]

if __name__ == "__main__":
    # The captured payload contains " → " separators; a Windows console defaults to cp1252
    # and would raise UnicodeEncodeError inside the debug print (a harness problem, not an
    # app one - the real repo writes to utf8mb4 MySQL). Done here rather than at module
    # scope so importing this module for its PATCHES doesn't clobber a caller's stdout.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    for p in PATCHES:
        p.start()
    app = create_app()

    @app.before_request
    def _auto_login():
        from flask import session
        session.setdefault("user_id", 2)
        session.setdefault("user_name", "Noriel Agno")
        session.setdefault("must_change_password", False)

    print("STUBBED server - DB is NOT used. Auto-logged-in as Noriel Agno (id 2).")
    app.run(debug=False, port=int(os.environ.get("PORT", 5057)))
