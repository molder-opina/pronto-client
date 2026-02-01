-- Agregar configuración para tiempo de retención de órdenes pagadas en panel activo
-- Si ya existe, no hace nada (ON DUPLICATE KEY UPDATE mantiene el valor existente)

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
    created_at,
    updated_at
) VALUES (
    'paid_orders_retention_minutes',
    '60',
    'int',
    'Parámetros Avanzados',
    'Tiempo de retención de órdenes pagadas',
    'Minutos que las órdenes pagadas permanecen visibles en el panel de órdenes activas antes de archivarse automáticamente',
    5,
    240,
    'minutos',
    NOW(),
    NOW()
) ON DUPLICATE KEY UPDATE
    config_key = config_key;  -- No actualiza nada si ya existe
