-- Migration: Create area management functions for restaurant floor management
-- Purpose: Create stored procedures for managing areas and table assignments
-- Created: 2026-01-31
-- Version: 1.0

-- Procedimiento para crear una nueva área
CREATE OR REPLACE FUNCTION create_area(
    p_name VARCHAR(120),
    p_description TEXT,
    p_color VARCHAR(20),
    p_prefix VARCHAR(10),
    p_background_image TEXT,
    p_is_active BOOLEAN DEFAULT TRUE
) RETURNS INT AS $$
DECLARE
    v_id INT;
BEGIN
    INSERT INTO pronto_areas (name, description, color, prefix, background_image, is_active)
    VALUES (p_name, p_description, p_color, p_prefix, p_background_image, p_is_active)
    RETURNING id;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para asignar un área a una mesa existente
CREATE OR REPLACE FUNCTION assign_table_to_area(
    p_table_id INT,
    p_area_id INT
) RETURNS VOID AS $$
BEGIN
    UPDATE pronto_tables
    SET area_id = p_area_id
    WHERE id = p_table_id;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para asignar un área a múltiples mesas (rango)
CREATE OR REPLACE FUNCTION assign_tables_to_area_by_range(
    p_table_ids INT[],
    p_area_id INT
) RETURNS VOID AS $$
BEGIN
    UPDATE pronto_tables
    SET area_id = p_area_id
    WHERE id = ANY(p_table_ids);
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para asignar área a mesas basándose en prefijo
CREATE OR REPLACE FUNCTION assign_tables_to_area_by_prefix(
    p_prefix VARCHAR(10),
    p_area_id INT
) RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE pronto_tables
    SET area_id = p_area_id
    WHERE table_number LIKE p_prefix || '%';
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para obtener todas las mesas de un área
CREATE OR REPLACE FUNCTION get_tables_by_area(
    p_area_id INT
) RETURNS TABLE (
    table_id INT,
    table_number VARCHAR(50),
    table_code VARCHAR(100),
    is_active BOOLEAN,
    area_name VARCHAR(120),
    area_color VARCHAR(20)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id,
        t.table_number,
        t.qr_code,
        t.is_active,
        a.name AS area_name,
        a.color AS area_color
    FROM pronto_tables t
    INNER JOIN pronto_areas a ON t.area_id = a.id
    WHERE a.id = p_area_id
    ORDER BY t.id;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para limpiar area_id de mesas cuando se elimina un área
CREATE OR REPLACE FUNCTION detach_tables_from_area(
    p_area_id INT
) RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE pronto_tables
    SET area_id = NULL
    WHERE area_id = p_area_id;
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para desactivar un área (no elimina mesas, solo marca como inactiva)
CREATE OR REPLACE FUNCTION deactivate_area(
    p_area_id INT
) RETURNS VOID AS $$
BEGIN
    UPDATE pronto_areas
    SET is_active = FALSE
    WHERE id = p_area_id;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para activar un área
CREATE OR REPLACE FUNCTION activate_area(
    p_area_id INT
) RETURNS VOID AS $$
BEGIN
    UPDATE pronto_areas
    SET is_active = TRUE
    WHERE id = p_area_id;
END;
$$ LANGUAGE plpgsql;

-- Procedimiento para obtener estadísticas de áreas
CREATE OR REPLACE FUNCTION get_area_statistics()
RETURNS TABLE (
    area_id INT,
    area_name VARCHAR(120),
    area_prefix VARCHAR(10),
    table_count INT,
    active_table_count INT,
    total_orders INT,
    active_sessions INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id AS area_id,
        a.name AS area_name,
        a.prefix AS area_prefix,
        COUNT(t.id) AS table_count,
        COUNT(t.id) FILTER (t.is_active = TRUE) AS active_table_count,
        COALESCE(
            (SELECT COUNT(*) FROM pronto_orders o
             INNER JOIN pronto_dining_sessions ds ON o.session_id = ds.id
             INNER JOIN pronto_tables t ON ds.table_id = t.id
             WHERE t.area_id = a.id),
            0
        ) AS total_orders,
        COALESCE(
            (SELECT COUNT(*) FROM pronto_dining_sessions ds
             INNER JOIN pronto_tables t ON ds.table_id = t.id
             WHERE t.area_id = a.id AND ds.status = 'open'),
            0
        ) AS active_sessions
    FROM pronto_areas a
    GROUP BY a.id, a.name, a.prefix
    ORDER BY a.prefix;
END;
$$ LANGUAGE plpgsql;

-- Comentario sobre la migración
COMMENT ON FUNCTION create_area IS 'Crea una nueva área/zona del restaurante';
COMMENT ON FUNCTION assign_table_to_area IS 'Asigna una mesa existente a un área específica';
COMMENT ON FUNCTION assign_tables_to_area_by_range IS 'Asigna múltiples mesas a un área mediante sus IDs';
COMMENT ON FUNCTION assign_tables_to_area_by_prefix IS 'Asigna mesas a un área basándose en el prefijo del número de mesa';
COMMENT ON FUNCTION get_tables_by_area IS 'Obtiene todas las mesas asignadas a un área con su información detallada';
COMMENT ON FUNCTION detach_tables_from_area IS 'Desvincula mesas de un área cuando se elimina (no elimina las mesas)';
COMMENT ON FUNCTION deactivate_area IS 'Marca un área como inactiva (no elimina el área)';
COMMENT ON FUNCTION activate_area IS 'Marca un área como activa';
COMMENT ON FUNCTION get_area_statistics IS 'Obtiene estadísticas de áreas y mesas (número de mesas, órdenes, sesiones activas)';
