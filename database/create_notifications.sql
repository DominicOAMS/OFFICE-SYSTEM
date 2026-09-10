-- In-app notification center. Deliberately lighter than the financial-record
-- shape (tbl_account_payables/tbl_check_vouchers) - a notification is never
-- edited after creation, only read, so it skips isDeleted/updatedBy/soft-delete
-- entirely, closer to tbl_purchase_order_item_allocations' lighter convention.

CREATE TABLE IF NOT EXISTS db_os_2026.tbl_notifications (
    id INT NOT NULL AUTO_INCREMENT,
    userId INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    body VARCHAR(255) NULL,
    url VARCHAR(255) NULL,
    isRead TINYINT(1) NOT NULL DEFAULT 0,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tbl_notifications_userId_isRead (userId, isRead),
    CONSTRAINT fk_tbl_notifications_user
        FOREIGN KEY (userId) REFERENCES db_os_2026.tbl_users (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
