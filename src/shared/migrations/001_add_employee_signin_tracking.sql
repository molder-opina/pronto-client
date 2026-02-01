-- Migration: Add employee sign-in and activity tracking
-- Date: 2025-01-10
-- Description: Adds signed_in_at and last_activity_at fields to employees table

USE pronto_db;

-- Add new columns to employees table
ALTER TABLE employees
ADD COLUMN signed_in_at DATETIME NULL AFTER created_at,
ADD COLUMN last_activity_at DATETIME NULL AFTER signed_in_at;

-- Add index for efficient querying of active employees
CREATE INDEX ix_employee_last_activity ON employees(last_activity_at) WHERE last_activity_at IS NOT NULL;

-- Log migration
INSERT INTO schema_migrations (version, description, executed_at)
VALUES ('001', 'Add employee sign-in and activity tracking', NOW())
ON DUPLICATE KEY UPDATE executed_at = NOW();
