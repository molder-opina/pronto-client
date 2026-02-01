-- Migration: Add additional_roles field to employees table
-- Purpose: Allow employees to have multiple roles (e.g., waiter + cashier)
-- Created: 2025-01-10

-- Add additional_roles column to store JSON array of extra roles
ALTER TABLE employees
ADD COLUMN additional_roles TEXT NULL
COMMENT 'JSON array of additional roles beyond primary role'
AFTER role;

-- Create index for better query performance
CREATE INDEX idx_employees_additional_roles ON employees(additional_roles(255));

-- Set default additional_roles for existing waiters (make them also cashiers by default)
UPDATE employees
SET additional_roles = '["cashier"]'
WHERE role = 'waiter' AND (additional_roles IS NULL OR additional_roles = '');

-- Commit the changes
COMMIT;
