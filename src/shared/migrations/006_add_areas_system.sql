-- Migration: Add areas/zones system for restaurant floor management
-- Purpose: Create pronto_areas table and link tables to areas
-- Created: 2026-01-09

-- Create pronto_areas table
CREATE TABLE IF NOT EXISTS pronto_areas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE COMMENT 'Area name (e.g., Terraza, Interior, VIP, Bar)',
    description TEXT NULL COMMENT 'Optional area description',
    color VARCHAR(20) NOT NULL DEFAULT '#ff6b35' COMMENT 'Color code for UI display',
    prefix VARCHAR(10) NOT NULL UNIQUE COMMENT 'Prefix for table codes (e.g., T, I, V, B)',
    background_image LONGTEXT NULL COMMENT 'Base64 encoded canvas image',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Whether area is active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_area_name (name),
    INDEX ix_area_prefix (prefix),
    INDEX ix_area_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Restaurant areas/zones configuration';

-- Add area_id to pronto_tables
ALTER TABLE pronto_tables
ADD COLUMN area_id INT NULL COMMENT 'Reference to pronto_areas.id'
AFTER qr_code;

-- Add foreign key constraint
ALTER TABLE pronto_tables
ADD CONSTRAINT fk_table_area
FOREIGN KEY (area_id) REFERENCES pronto_areas(id)
ON DELETE SET NULL
ON UPDATE CASCADE;

-- Add index for better query performance
CREATE INDEX ix_table_area ON pronto_tables(area_id);

-- Insert default areas based on existing zones
INSERT INTO pronto_areas (name, description, color, prefix, is_active)
SELECT DISTINCT
    zone AS name,
    CONCAT('Área ', zone) AS description,
    CASE
        WHEN LOWER(zone) LIKE '%terr%' THEN '#4CAF50'
        WHEN LOWER(zone) LIKE '%inter%' THEN '#2196F3'
        WHEN LOWER(zone) LIKE '%vip%' THEN '#9C27B0'
        WHEN LOWER(zone) LIKE '%bar%' THEN '#FF9800'
        ELSE '#ff6b35'
    END AS color,
    CASE
        WHEN LOWER(zone) LIKE '%terr%' THEN 'T'
        WHEN LOWER(zone) LIKE '%inter%' THEN 'I'
        WHEN LOWER(zone) LIKE '%vip%' THEN 'V'
        WHEN LOWER(zone) LIKE '%bar%' THEN 'B'
        ELSE LEFT(UPPER(zone), 1)
    END AS prefix,
    TRUE AS is_active
FROM pronto_tables
WHERE zone IS NOT NULL AND zone != ''
ON DUPLICATE KEY UPDATE name=name;

-- Link existing tables to their corresponding areas
UPDATE pronto_tables t
INNER JOIN pronto_areas a ON t.zone = a.name
SET t.area_id = a.id
WHERE t.zone IS NOT NULL AND t.zone != '';

-- Commit the changes
COMMIT;
