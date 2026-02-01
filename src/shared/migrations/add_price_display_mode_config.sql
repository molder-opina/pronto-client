-- Migration: Add price display mode configuration
-- Description: Adds configuration for how prices are displayed (with or without tax)
-- Date: 2025-12-01

-- Add the price display mode configuration
INSERT INTO business_config (
    config_key,
    config_value,
    value_type,
    category,
    display_name,
    description,
    unit,
    updated_at
) VALUES (
    'price_display_mode',
    'tax_included',
    'string',
    'Parámetros Avanzados',
    'Método de presentación de precios',
    'Define cómo se muestran los precios al cliente. "tax_included" (recomendado para México y LATAM): Los precios mostrados ya incluyen IVA y la factura desglosará subtotal + IVA sin modificar el precio final. "tax_excluded" (para eventos/empresas): Los precios se muestran sin IVA y se suma al final en el ticket.',
    NULL,
    NOW()
) ON DUPLICATE KEY UPDATE
    config_key = config_key;  -- No actualiza nada si ya existe

-- Note: Valid values are 'tax_included' or 'tax_excluded'
-- 'tax_included' = Precio mostrado con IVA incluido (modo recomendado para México y LATAM)
-- 'tax_excluded' = Precio mostrado sin IVA (modo usado en menús para eventos o empresas)
