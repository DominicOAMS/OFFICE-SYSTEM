-- Migration: db_oams_app_2026.tbl_users -> db_os_2026.tbl_users
-- Creates db_os_2026 and a new tbl_users table, then copies data from the legacy database.
-- Source column mapping:
--   ID -> id, Name -> name, Email -> email, Pword -> password, Position -> position,
--   Collector -> collector, Links -> privileges, Branch -> branch
-- New tracking columns (not present in source) are defaulted: isDeleted=0, createdBy/updatedBy=NULL, timestamps=NOW().

CREATE DATABASE IF NOT EXISTS db_os_2026
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_users (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NULL,
    email VARCHAR(255) NULL,
    password VARCHAR(255) NULL,
    position VARCHAR(255) NULL,
    collector SMALLINT NOT NULL DEFAULT 0,
    privileges TEXT NULL,
    branch VARCHAR(255) NULL,
    isDeleted TINYINT(1) NOT NULL DEFAULT 0,
    createdBy INT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedBy INT NULL,
    updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_users
    (id, name, email, password, position, collector, privileges, branch, isDeleted, createdBy, createdAt, updatedBy, updatedAt)
SELECT
    ID, Name, Email, Pword, Position, Collector, Links, Branch,
    0 AS isDeleted, NULL AS createdBy, NOW() AS createdAt, NULL AS updatedBy, NOW() AS updatedAt
FROM db_oams_app_2026.tbl_users;
-- Note: InnoDB auto-advances the AUTO_INCREMENT counter past explicit ids inserted above,
-- so future inserts will continue after the highest migrated id.
