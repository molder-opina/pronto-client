-- Migration: Add closed sessions history configuration
-- Created: 2025-11-10
-- Description: Add configuration parameter for closed sessions history retention period

INSERT INTO business_config (
    config_key,
    config_value,
    value_type,
    category,
    display_name,
    description,
    min_value,
    max_value,
    unit,
    updated_at
) VALUES (
    'closed_sessions_history_hours',
    '24',
    'int',
    'operations',
    'Historial de órdenes cerradas',
    'Número de horas que se mantiene visible el historial de órdenes cerradas para los meseros. Las órdenes cerradas dentro de este período pueden ser reimpresas o reenviadas.',
    1,
    168,
    'hours',
    NOW()
) ON DUPLICATE KEY UPDATE
    config_value = VALUES(config_value),
    display_name = VALUES(display_name),
    description = VALUES(description),
    min_value = VALUES(min_value),
    max_value = VALUES(max_value),
    unit = VALUES(unit),
    updated_at = NOW();

-- Track migration
INSERT INTO schema_migrations (version, applied_at)
VALUES ('003_add_closed_sessions_history_config', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
