-- Adds the flag used to force a password change on next login
-- (used for the bulk default-password reset and for admin-generated temp passwords).
ALTER TABLE db_os_2026.tbl_users
    ADD COLUMN mustChangePassword TINYINT(1) NOT NULL DEFAULT 0 AFTER password;
