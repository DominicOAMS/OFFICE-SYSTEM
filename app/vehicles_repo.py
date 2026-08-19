from .db import get_connection


def list_active_vehicles():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.*, u.name AS assignedUserName
                FROM tbl_vehicles v
                LEFT JOIN tbl_users u ON u.id = v.assignedUserId
                WHERE v.isDeleted = 0 AND v.status = 'Active'
                ORDER BY v.plateNumber ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_vehicle(vehicle_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tbl_vehicles WHERE id = %s LIMIT 1", (vehicle_id,))
            return cur.fetchone()
    finally:
        conn.close()


def create_vehicle(data, created_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tbl_vehicles
                    (plateNumber, vehicleModel, fuelType, fuelEfficiencyKmPerLiter, fuelPriceCategory,
                     assignedUserId, status, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
                VALUES
                    (%s, %s, %s, %s, %s,
                     %s, %s, 0, %s, NOW(), %s, NOW())
                """,
                (
                    data["plateNumber"],
                    data["vehicleModel"],
                    data["fuelType"],
                    data["fuelEfficiencyKmPerLiter"],
                    data["fuelPriceCategory"],
                    data["assignedUserId"],
                    data["status"],
                    created_by,
                    created_by,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_vehicle(vehicle_id, data, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tbl_vehicles
                SET plateNumber = %s, vehicleModel = %s, fuelType = %s, fuelEfficiencyKmPerLiter = %s,
                    fuelPriceCategory = %s, assignedUserId = %s, status = %s,
                    updatedBy = %s, updatedAt = NOW()
                WHERE id = %s
                """,
                (
                    data["plateNumber"],
                    data["vehicleModel"],
                    data["fuelType"],
                    data["fuelEfficiencyKmPerLiter"],
                    data["fuelPriceCategory"],
                    data["assignedUserId"],
                    data["status"],
                    updated_by,
                    vehicle_id,
                ),
            )
    finally:
        conn.close()


def soft_delete_vehicle(vehicle_id, updated_by):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_vehicles SET isDeleted = 1, updatedBy = %s, updatedAt = NOW() WHERE id = %s",
                (updated_by, vehicle_id),
            )
    finally:
        conn.close()
