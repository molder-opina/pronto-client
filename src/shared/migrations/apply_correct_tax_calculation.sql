-- Apply correct tax calculation to all existing orders
-- This fixes the double-tax issue where tax was being added on top of prices that already included tax
-- Date: 2025-12-01

-- Backup current values (optional, comment out if not needed)
CREATE TABLE IF NOT EXISTS orders_backup_20251201 AS
SELECT * FROM orders WHERE 1=0;

INSERT INTO orders_backup_20251201
SELECT * FROM orders;

-- Update orders with correct tax calculation
-- For tax_included mode: price / 1.16 = base_price, then base_price * 0.16 = tax

UPDATE orders o
SET
    o.subtotal = ROUND((
        SELECT SUM(
            (oi.unit_price / 1.16) * oi.quantity +
            COALESCE((
                SELECT SUM((oim.unit_price_adjustment / 1.16) * oim.quantity)
                FROM order_item_modifiers oim
                WHERE oim.order_item_id = oi.id
            ), 0)
        )
        FROM order_items oi
        WHERE oi.order_id = o.id
    ), 2),
    o.tax_amount = ROUND((
        SELECT SUM(
            (oi.unit_price / 1.16) * oi.quantity +
            COALESCE((
                SELECT SUM((oim.unit_price_adjustment / 1.16) * oim.quantity)
                FROM order_item_modifiers oim
                WHERE oim.order_item_id = oi.id
            ), 0)
        )
        FROM order_items oi
        WHERE oi.order_id = o.id
    ) * 0.16, 2)
WHERE o.workflow_status != 'cancelled';

-- Update total_amount = subtotal + tax_amount + tip_amount
UPDATE orders
SET total_amount = subtotal + tax_amount + COALESCE(tip_amount, 0)
WHERE workflow_status != 'cancelled';

-- Recompute dining session totals
UPDATE dining_sessions ds
SET
    ds.subtotal = COALESCE((
        SELECT SUM(o.subtotal)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ), 0),
    ds.tax_amount = COALESCE((
        SELECT SUM(o.tax_amount)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ), 0),
    ds.total_amount = COALESCE((
        SELECT SUM(o.total_amount)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ), 0) + COALESCE(ds.tip_amount, 0)
WHERE ds.status = 'open';

-- Show summary
SELECT
    '✅ Tax calculation corrected' as status,
    COUNT(*) as orders_updated
FROM orders
WHERE workflow_status != 'cancelled';

-- Show sample of corrected orders
SELECT
    o.id as order_id,
    CONCAT('$', FORMAT(o.subtotal, 2)) as subtotal,
    CONCAT('$', FORMAT(o.tax_amount, 2)) as tax,
    CONCAT('$', FORMAT(o.total_amount, 2)) as total
FROM orders o
WHERE o.workflow_status != 'cancelled'
ORDER BY o.id DESC
LIMIT 5;
