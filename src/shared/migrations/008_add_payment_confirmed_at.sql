-- Migration: Add payment_confirmed_at column to dining_sessions
-- Created: 2025-11-18
-- Description: Add missing column for payment confirmation timestamp

USE pronto;

-- Add payment_confirmed_at column
ALTER TABLE dining_sessions
ADD COLUMN payment_confirmed_at DATETIME NULL;

-- Track migration
INSERT INTO schema_migrations (version, applied_at)
VALUES ('008_add_payment_confirmed_at', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
