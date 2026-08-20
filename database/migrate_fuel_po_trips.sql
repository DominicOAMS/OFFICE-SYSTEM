-- A Fuel PO stops being "one journey" and becomes a container of MULTIPLE DATED TRIPS.
-- Each trip carries its own date, its own starting point, its own ordered stops and its
-- own fuel estimate + amount; the PO's amountRequested becomes the sum of its trips.
-- Vehicle and fuelEfficiencyKmPerLiter stay PO-level (one vehicle per request).
--
-- Notes on the data (profiled before writing this):
--   * tbl_fuel_pos holds ~1,079 rows. 1,078 (id 1..1081) are migrated legacy history from
--     migrate_fuel_po.sql: NULL startLocation/startLat/startLng/fuelEfficiencyKmPerLiter/
--     estimated*, and a `destination` column holding free text like "STRH & for whole week"
--     with no coordinates anywhere. Only a couple of rows came through the new map flow.
--   * tbl_fuel_po_destinations already exists (migrate_fuel_estimation_v2.sql) and was
--     empty at authoring time. It has always been write-only - every screen reads the
--     denormalized tbl_fuel_pos.destination string instead. This migration re-parents it
--     onto trips, but is written to be safe even if it is NOT empty when it runs: tripId
--     is added NULL-able, backfilled, and only tightened to NOT NULL by the companion
--     migrate_fuel_po_trips_tighten.sql once the new app code is deployed.
--   * EVERY existing PO gets exactly one trip, including the 1,078 legacy rows whose trip
--     will have a NULL start and zero destination children. That is deliberate: it keeps
--     the read path single-shaped (a PO always has >= 1 trip) instead of forcing every
--     consumer to carry a "PO with no trips" fallback branch forever. No information is
--     invented and none is lost - the legacy free-text itinerary rides along on the trip's
--     own `destination` column, which is exactly what the View modal shows today.
--   * PO-level startLocation/destination/estimated*/amountRequested are KEPT and keep being
--     written as rollups, so the list page, the View modal's data-* attributes and
--     _filter_clauses' `destination LIKE` all keep working unchanged.
--   * requestDate keeps meaning "the date this request was made" - it is NOT redefined to
--     the travel date. All 1,078 legacy rows carry a genuine historical request date, and
--     redefining the column would make old and new rows mean different things. Travel dates
--     live on tbl_fuel_po_trips.tripDate.
--   * No column is dropped and no row is deleted. Re-running is a no-op.

-- --------------------------------------------------------------- 1. the trips table
-- No audit columns, deliberately matching sibling tbl_fuel_po_destinations: trips are
-- wholly-owned children, written in the same operation as the parent, cascade-deleted with
-- it, never addressed by their own URL. Their who/when IS tbl_fuel_pos.createdBy/createdAt.
CREATE TABLE IF NOT EXISTS db_os_2026.tbl_fuel_po_trips (
    id INT NOT NULL AUTO_INCREMENT,
    fuelPoId INT NOT NULL,
    sequence INT NOT NULL,
    tripDate DATE NOT NULL,
    startLocation VARCHAR(255) NULL,
    startLat DECIMAL(10,7) NULL,
    startLng DECIMAL(10,7) NULL,
    destination VARCHAR(255) NULL,
    estimatedDistanceKm DECIMAL(7,2) NULL,
    estimatedAmount DECIMAL(12,2) NULL,
    amountRequested DECIMAL(12,2) NULL,
    PRIMARY KEY (id),
    -- sequence is the ORDER BY key for the whole read path; a duplicate would make
    -- "Trip 1 / Trip 2" render nondeterministically on a money document. Also serves
    -- fuelPoId lookups via leftmost prefix, so no separate index on fuelPoId is needed.
    UNIQUE KEY uq_tbl_fuel_po_trips_fuelPo_sequence (fuelPoId, sequence),
    -- Not for uniqueness (id is already PK) - exists solely so tbl_fuel_po_destinations
    -- can hang a composite FK off it in step 3.
    UNIQUE KEY uq_tbl_fuel_po_trips_id_fuelPoId (id, fuelPoId),
    CONSTRAINT fk_tbl_fuel_po_trips_fuelPo
        FOREIGN KEY (fuelPoId) REFERENCES db_os_2026.tbl_fuel_pos (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------- 2. backfill one trip per existing PO
-- No isDeleted filter: soft-deleted POs get their trip too, so undeleting one never
-- produces a PO with no trips. NOT EXISTS makes a re-run a no-op (and the unique key on
-- (fuelPoId, sequence) would reject a duplicate anyway).
INSERT INTO db_os_2026.tbl_fuel_po_trips
    (fuelPoId, sequence, tripDate, startLocation, startLat, startLng,
     destination, estimatedDistanceKm, estimatedAmount, amountRequested)
SELECT
    fp.id,
    1,
    fp.requestDate,
    fp.startLocation,
    fp.startLat,
    fp.startLng,
    fp.destination,
    fp.estimatedDistanceKm,
    fp.estimatedAmount,
    fp.amountRequested
FROM db_os_2026.tbl_fuel_pos fp
WHERE NOT EXISTS (
    SELECT 1 FROM db_os_2026.tbl_fuel_po_trips t WHERE t.fuelPoId = fp.id
);

-- ---------------------------------------- 3. hang destinations off a trip, not the PO
-- tripId is added NULL-able on purpose (see header). fuelPoId is KEPT, not replaced: it
-- is what lets the list page fetch one page's stops with a single WHERE fuelPoId IN (...)
-- instead of joining through trips, and the composite FK below makes the two columns
-- self-consistent rather than merely conventionally so.
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_po_destinations'
      AND COLUMN_NAME = 'tripId'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_po_destinations ADD COLUMN tripId INT NULL AFTER fuelPoId',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Expected to touch 0 rows today, but written so that any rows created by the old code
-- between this migration and the app deploy land on their PO's only trip.
UPDATE db_os_2026.tbl_fuel_po_destinations d
JOIN db_os_2026.tbl_fuel_po_trips t
    ON t.fuelPoId = d.fuelPoId AND t.sequence = 1
SET d.tripId = t.id
WHERE d.tripId IS NULL;

-- sequence now restarts at 1 within each trip rather than running across the whole PO.
-- The table shipped with no uniqueness guard on ordering at all; at 0 rows we close that
-- gap for free.
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_po_destinations'
      AND INDEX_NAME = 'uq_tbl_fuel_po_destinations_trip_sequence'
);
SET @sql = IF(@has_idx = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_po_destinations
        ADD UNIQUE KEY uq_tbl_fuel_po_destinations_trip_sequence (tripId, sequence)',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- The composite FK is what makes keeping both tripId and fuelPoId safe: it guarantees
-- tripId is real AND that fuelPoId matches that trip's own PO, so the denormalization
-- can't drift. Valid while tripId is still NULL-able (MySQL MATCH SIMPLE passes a row
-- with a NULL FK column).
SET @has_fk = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = 'db_os_2026' AND TABLE_NAME = 'tbl_fuel_po_destinations'
      AND CONSTRAINT_NAME = 'fk_tbl_fuel_po_destinations_trip'
);
SET @sql = IF(@has_fk = 0,
    'ALTER TABLE db_os_2026.tbl_fuel_po_destinations
        ADD CONSTRAINT fk_tbl_fuel_po_destinations_trip
        FOREIGN KEY (tripId, fuelPoId)
        REFERENCES db_os_2026.tbl_fuel_po_trips (id, fuelPoId)
        ON DELETE CASCADE ON UPDATE CASCADE',
    'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
