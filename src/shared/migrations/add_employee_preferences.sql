-- Migration: Add preferences column to employees table
-- Description: Adds a TEXT column to store employee preferences as JSON
-- Date: 2025-12-03

-- Add preferences column to employees table
ALTER TABLE employees
ADD COLUMN preferences TEXT NULL DEFAULT '{}'
COMMENT 'Employee preferences stored as JSON (card size, filters, etc.)';

-- Create index for faster lookups (optional but recommended)
-- Note: MySQL cannot index TEXT columns directly, but we can add a generated column if needed
-- For now, we'll just add the column and let the application handle JSON parsing
