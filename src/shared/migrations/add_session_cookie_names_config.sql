-- Agregar configuraciones para nombres de cookies de sesión
-- Permite configurar nombres diferentes para cookies de clientes y empleados
-- para evitar conflictos de sesión entre aplicaciones

INSERT INTO business_config (
    config_key,
    config_value,
    value_type,
    category,
    display_name,
    description,
    updated_at
) VALUES (
    'client_session_cookie_name',
    'pronto_client',
    'string',
    'security',
    'Nombre de cookie de clientes',
    'Nombre de la cookie de sesión para la aplicación de clientes. Cambiar este valor requiere reiniciar la aplicación.',
    NOW()
) ON DUPLICATE KEY UPDATE
    config_key = config_key;  -- No actualiza nada si ya existe

INSERT INTO business_config (
    config_key,
    config_value,
    value_type,
    category,
    display_name,
    description,
    updated_at
) VALUES (
    'employee_session_cookie_name',
    'pronto_employee',
    'string',
    'security',
    'Nombre de cookie de empleados',
    'Nombre de la cookie de sesión para la aplicación de empleados. Cambiar este valor requiere reiniciar la aplicación.',
    NOW()
) ON DUPLICATE KEY UPDATE
    config_key = config_key;  -- No actualiza nada si ya existe
