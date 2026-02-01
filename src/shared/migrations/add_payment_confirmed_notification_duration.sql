-- Agregar configuración para duración del mensaje de confirmación de pago
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
    'payment_confirmed_duration_seconds',
    '5',
    'int',
    'Parámetros Avanzados',
    'Duración del mensaje de pago confirmado',
    'Segundos que el mensaje de confirmación de pago se muestra al cliente antes de recargar la página',
    1,
    30,
    'segundos',
    NOW(),
    NOW()
) ON DUPLICATE KEY UPDATE
    config_key = config_key;  -- No actualiza nada si ya existe
