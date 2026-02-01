-- Migration: Add business configuration, roles, and feedback tables
-- Purpose: Add comprehensive business configuration system
-- Created: 2025-01-12

-- ============================================================
-- Business Info Table
-- ============================================================
CREATE TABLE IF NOT EXISTS business_info (
    id INT PRIMARY KEY AUTO_INCREMENT,
    business_name VARCHAR(200) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    phone VARCHAR(50),
    email VARCHAR(200),
    website VARCHAR(200),
    logo_url VARCHAR(500),
    description TEXT,
    currency VARCHAR(10) NOT NULL DEFAULT 'MXN',
    timezone VARCHAR(50) NOT NULL DEFAULT 'America/Mexico_City',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by INT,
    FOREIGN KEY (updated_by) REFERENCES employees(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Business Schedule Table
-- ============================================================
CREATE TABLE IF NOT EXISTS business_schedule (
    id INT PRIMARY KEY AUTO_INCREMENT,
    day_of_week INT NOT NULL,
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    open_time VARCHAR(10),
    close_time VARCHAR(10),
    notes VARCHAR(200),
    CONSTRAINT check_day_of_week_range CHECK (day_of_week >= 0 AND day_of_week <= 6),
    INDEX ix_business_schedule_day (day_of_week)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Custom Roles Table
-- ============================================================
CREATE TABLE IF NOT EXISTS custom_roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    role_code VARCHAR(64) NOT NULL UNIQUE,
    role_name VARCHAR(100) NOT NULL,
    description TEXT,
    color VARCHAR(20),
    icon VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by INT,
    FOREIGN KEY (created_by) REFERENCES employees(id) ON DELETE SET NULL,
    INDEX ix_custom_role_code (role_code),
    INDEX ix_custom_role_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Role Permissions Table
-- ============================================================
CREATE TABLE IF NOT EXISTS role_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    custom_role_id INT NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT TRUE,
    conditions TEXT,
    FOREIGN KEY (custom_role_id) REFERENCES custom_roles(id) ON DELETE CASCADE,
    INDEX ix_role_permission_role (custom_role_id),
    INDEX ix_role_permission_resource (resource_type, action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Feedback Table
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_id INT NOT NULL,
    customer_id INT,
    employee_id INT,
    category VARCHAR(50) NOT NULL,
    rating INT NOT NULL,
    comment TEXT,
    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES dining_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL,
    CONSTRAINT check_rating_range CHECK (rating >= 1 AND rating <= 5),
    INDEX ix_feedback_session (session_id),
    INDEX ix_feedback_employee (employee_id),
    INDEX ix_feedback_category (category),
    INDEX ix_feedback_rating (rating),
    INDEX ix_feedback_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Insert Default Data
-- ============================================================

-- Insert default business info (if none exists)
INSERT INTO business_info (business_name, currency, timezone)
SELECT 'Mi Restaurante', 'MXN', 'America/Mexico_City'
WHERE NOT EXISTS (SELECT 1 FROM business_info LIMIT 1);

-- Insert default schedule (Monday-Sunday, 9 AM - 10 PM)
INSERT INTO business_schedule (day_of_week, is_open, open_time, close_time)
SELECT day, TRUE, '09:00', '22:00'
FROM (
    SELECT 0 as day UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
    SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
) days
WHERE NOT EXISTS (
    SELECT 1 FROM business_schedule WHERE day_of_week = days.day
);

-- ============================================================
-- Initialize Default System Settings
-- ============================================================

-- Add default settings if they don't exist
INSERT INTO system_settings (key, value, value_type, description, category)
SELECT 'show_estimated_time', 'true', 'bool',
    'Mostrar tiempo estimado de preparación en resumen de pedidos', 'orders'
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key = 'show_estimated_time');

INSERT INTO system_settings (key, value, value_type, description, category)
SELECT 'estimated_time_min', '25', 'int',
    'Tiempo estimado mínimo de preparación (minutos)', 'orders'
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key = 'estimated_time_min');

INSERT INTO system_settings (key, value, value_type, description, category)
SELECT 'estimated_time_max', '30', 'int',
    'Tiempo estimado máximo de preparación (minutos)', 'orders'
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key = 'estimated_time_max');

-- ============================================================
-- Create Example Custom Role (Optional)
-- ============================================================

-- Insert a sample custom role: "Gerente de Turno"
INSERT INTO custom_roles (role_code, role_name, description, color, icon, is_active)
SELECT 'shift_manager', 'Gerente de Turno',
    'Gerente con permisos para supervisar operaciones durante su turno',
    '#4F46E5', 'user-shield', TRUE
WHERE NOT EXISTS (SELECT 1 FROM custom_roles WHERE role_code = 'shift_manager');

-- Add permissions for shift manager
INSERT INTO role_permissions (custom_role_id, resource_type, action, allowed)
SELECT
    (SELECT id FROM custom_roles WHERE role_code = 'shift_manager'),
    resource, act, TRUE
FROM (
    SELECT 'orders' as resource, 'read' as act UNION ALL
    SELECT 'orders', 'update' UNION ALL
    SELECT 'orders', 'approve' UNION ALL
    SELECT 'sessions', 'read' UNION ALL
    SELECT 'sessions', 'update' UNION ALL
    SELECT 'employees', 'read' UNION ALL
    SELECT 'reports', 'read'
) perms
WHERE EXISTS (SELECT 1 FROM custom_roles WHERE role_code = 'shift_manager')
AND NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    JOIN custom_roles cr ON cr.id = rp.custom_role_id
    WHERE cr.role_code = 'shift_manager'
    AND rp.resource_type = perms.resource
    AND rp.action = perms.act
);

-- ============================================================
-- Commit Changes
-- ============================================================
COMMIT;

-- ============================================================
-- Verification Queries (Optional - for manual verification)
-- ============================================================
-- Uncomment to verify the migration:

-- SELECT 'business_info' as table_name, COUNT(*) as count FROM business_info
-- UNION ALL
-- SELECT 'business_schedule', COUNT(*) FROM business_schedule
-- UNION ALL
-- SELECT 'custom_roles', COUNT(*) FROM custom_roles
-- UNION ALL
-- SELECT 'role_permissions', COUNT(*) FROM role_permissions
-- UNION ALL
-- SELECT 'feedback', COUNT(*) FROM feedback;
