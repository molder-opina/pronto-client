-- Migration: Create configurable day periods and menu item assignments
-- Created: 2025-02-14
-- Description: Adds day_periods and menu_item_day_periods tables plus migrates existing breakfast/afternoon/night flags.

USE pronto_db;

-- Create master table for day periods
CREATE TABLE IF NOT EXISTS day_periods (
    id INT PRIMARY KEY AUTO_INCREMENT,
    period_key VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description TEXT NULL,
    icon VARCHAR(16) NULL,
    color VARCHAR(32) NULL,
    start_time CHAR(5) NOT NULL,
    end_time CHAR(5) NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_day_period_display_order (display_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create link table for menu item assignments
CREATE TABLE IF NOT EXISTS menu_item_day_periods (
    id INT PRIMARY KEY AUTO_INCREMENT,
    menu_item_id INT NOT NULL,
    period_id INT NOT NULL,
    tag_type VARCHAR(32) NOT NULL DEFAULT 'recommendation',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_menu_item_period_tag (menu_item_id, period_id, tag_type),
    INDEX ix_menu_item_period_menu (menu_item_id),
    INDEX ix_menu_item_period_tag (tag_type),
    CONSTRAINT fk_menu_item_period_item FOREIGN KEY (menu_item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
    CONSTRAINT fk_menu_item_period_period FOREIGN KEY (period_id) REFERENCES day_periods(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default periods if they do not exist
INSERT INTO day_periods (period_key, name, icon, color, start_time, end_time, display_order, is_default)
SELECT * FROM (SELECT 'breakfast' AS period_key, 'Mañana' AS name, '☕' AS icon, '#f97316' AS color, '06:00' AS start_time, '12:00' AS end_time, 1 AS display_order, 1 AS is_default) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM day_periods WHERE period_key = 'breakfast');

INSERT INTO day_periods (period_key, name, icon, color, start_time, end_time, display_order, is_default)
SELECT * FROM (SELECT 'afternoon', 'Tarde', '🌮', '#0ea5e9', '12:00', '18:00', 2, 1) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM day_periods WHERE period_key = 'afternoon');

INSERT INTO day_periods (period_key, name, icon, color, start_time, end_time, display_order, is_default)
SELECT * FROM (SELECT 'night', 'Noche', '🌙', '#6366f1', '18:00', '06:00', 3, 1) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM day_periods WHERE period_key = 'night');

-- Migrate existing recommendation flags into the new assignment table
INSERT INTO menu_item_day_periods (menu_item_id, period_id, tag_type)
SELECT id AS menu_item_id,
       (SELECT id FROM day_periods WHERE period_key = 'breakfast') AS period_id,
       'recommendation' AS tag_type
FROM menu_items
WHERE is_breakfast_recommended = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM menu_item_day_periods mip
      WHERE mip.menu_item_id = menu_items.id
        AND mip.period_id = (SELECT id FROM day_periods WHERE period_key = 'breakfast')
        AND mip.tag_type = 'recommendation'
  );

INSERT INTO menu_item_day_periods (menu_item_id, period_id, tag_type)
SELECT id AS menu_item_id,
       (SELECT id FROM day_periods WHERE period_key = 'afternoon') AS period_id,
       'recommendation' AS tag_type
FROM menu_items
WHERE is_afternoon_recommended = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM menu_item_day_periods mip
      WHERE mip.menu_item_id = menu_items.id
        AND mip.period_id = (SELECT id FROM day_periods WHERE period_key = 'afternoon')
        AND mip.tag_type = 'recommendation'
  );

INSERT INTO menu_item_day_periods (menu_item_id, period_id, tag_type)
SELECT id AS menu_item_id,
       (SELECT id FROM day_periods WHERE period_key = 'night') AS period_id,
       'recommendation' AS tag_type
FROM menu_items
WHERE is_night_recommended = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM menu_item_day_periods mip
      WHERE mip.menu_item_id = menu_items.id
        AND mip.period_id = (SELECT id FROM day_periods WHERE period_key = 'night')
        AND mip.tag_type = 'recommendation'
  );

-- Track migration
INSERT INTO schema_migrations (version, applied_at)
VALUES ('007_add_day_periods', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
