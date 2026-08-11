-- Migration: db_oams_app_2026.tbl_program_folder / tbl_program_menu -> db_os_2026.tbl_users_folder / tbl_users_menu
-- These back the "Allowed Links" privileges picker on the User Accounts page
-- (grouped checkbox list, matching the legacy Laravel admin's Users page).

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_users_folder (
    id VARCHAR(255) NOT NULL,
    pf_label VARCHAR(255) NULL,
    pf_icon VARCHAR(255) NULL,
    pf_order INT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_users_menu (
    id INT NOT NULL AUTO_INCREMENT,
    pm_label VARCHAR(255) NULL,
    pm_icon VARCHAR(255) NULL,
    pm_link VARCHAR(255) NULL,
    pm_folder_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO db_os_2026.tbl_users_folder (id, pf_label, pf_icon, pf_order)
SELECT id, pf_label, pf_icon, pf_order FROM db_oams_app_2026.tbl_program_folder;

INSERT INTO db_os_2026.tbl_users_menu (id, pm_label, pm_icon, pm_link, pm_folder_id)
SELECT id, pm_label, pm_icon, pm_link, pm_folder_id FROM db_oams_app_2026.tbl_program_menu;
