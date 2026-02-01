-- Migration: Add check_requested_at column to dining_sessions
-- Created: 2025-11-13
-- Description: Add check_requested_at timestamp to track when check/bill was requested

USE pronto_db;

-- Add check_requested_at column to dining_sessions
ALTER TABLE dining_sessions
ADD COLUMN IF NOT EXISTS check_requested_at DATETIME NULL
COMMENT 'Timestamp when the customer requested the check/bill';

-- Track migration
INSERT INTO schema_migrations (version, applied_at)
VALUES ('006_add_check_requested_at_column', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
