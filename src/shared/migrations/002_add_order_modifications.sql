-- Migration: Add order modification system
-- Date: 2025-01-10
-- Description: Creates order_modifications table to track customer and waiter modification requests

USE pronto_db;

-- Create order_modifications table
CREATE TABLE IF NOT EXISTS order_modifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,

    -- Who initiated the modification
    initiated_by_role VARCHAR(32) NOT NULL COMMENT 'customer or waiter',
    initiated_by_customer_id INT NULL,
    initiated_by_employee_id INT NULL,

    -- Status of the modification
    status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending, approved, rejected, applied',

    -- JSON structure containing the changes
    changes_data TEXT NOT NULL COMMENT 'JSON with items_to_add, items_to_remove, items_to_update',

    -- Who reviewed the modification (for waiter-initiated changes)
    reviewed_by_customer_id INT NULL,
    reviewed_by_employee_id INT NULL,

    -- Timestamps
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    applied_at DATETIME NULL,

    -- Foreign keys
    CONSTRAINT fk_order_modification_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_order_modification_initiator_customer FOREIGN KEY (initiated_by_customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    CONSTRAINT fk_order_modification_initiator_employee FOREIGN KEY (initiated_by_employee_id) REFERENCES employees(id) ON DELETE SET NULL,
    CONSTRAINT fk_order_modification_reviewer_customer FOREIGN KEY (reviewed_by_customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    CONSTRAINT fk_order_modification_reviewer_employee FOREIGN KEY (reviewed_by_employee_id) REFERENCES employees(id) ON DELETE SET NULL,

    -- Indexes for performance
    INDEX ix_order_modification_order (order_id),
    INDEX ix_order_modification_status (status),
    INDEX ix_order_modification_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Log migration
INSERT INTO schema_migrations (version, description, executed_at)
VALUES ('002', 'Add order modification system', NOW())
ON DUPLICATE KEY UPDATE executed_at = NOW();
