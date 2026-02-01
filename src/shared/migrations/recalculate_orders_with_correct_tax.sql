-- Migration: Recalculate order totals with correct tax logic
-- Description: Fixes orders that were created with incorrect tax calculation
-- Date: 2025-12-01
--
-- This script recalculates order totals for the tax_included mode where:
-- - Price displayed already includes tax
-- - Subtotal = price_base (without tax)
-- - Tax = subtotal * tax_rate
-- - Total = subtotal + tax
--
-- For tax_rate = 0.16 (16%):
-- - If display_price = $9.50, then:
--   - price_base = $9.50 / 1.16 = $8.19
--   - tax = $8.19 * 0.16 = $1.31
--   - total = $8.19 + $1.31 = $9.50

-- Create a temporary table to store correct calculations
CREATE TEMPORARY TABLE IF NOT EXISTS order_recalc AS
SELECT
    o.id as order_id,
    o.subtotal as old_subtotal,
    o.tax_amount as old_tax,
    o.total_amount as old_total,
    -- Calculate correct base price (remove tax from displayed price)
    ROUND(SUM(
        (oi.unit_price / 1.16) * oi.quantity +
        COALESCE((
            SELECT SUM((oim.unit_price_adjustment / 1.16) * oim.quantity)
            FROM order_item_modifiers oim
            WHERE oim.order_item_id = oi.id
        ), 0)
    ), 2) as new_subtotal,
    -- Calculate tax on base price
    ROUND(SUM(
        (oi.unit_price / 1.16) * oi.quantity +
        COALESCE((
            SELECT SUM((oim.unit_price_adjustment / 1.16) * oim.quantity)
            FROM order_item_modifiers oim
            WHERE oim.order_item_id = oi.id
        ), 0)
    ) * 0.16, 2) as new_tax,
    o.tip_amount as tip
FROM orders o
INNER JOIN order_items oi ON o.id = oi.order_id
WHERE o.workflow_status != 'cancelled'
GROUP BY o.id;

-- Add calculated total
UPDATE order_recalc
SET @new_total := new_subtotal + new_tax + COALESCE(tip, 0);

-- Show what would change (for verification)
SELECT
    order_id,
    CONCAT('$', FORMAT(old_subtotal, 2)) as old_subtotal,
    CONCAT('$', FORMAT(old_tax, 2)) as old_tax,
    CONCAT('$', FORMAT(old_total, 2)) as old_total,
    CONCAT('$', FORMAT(new_subtotal, 2)) as new_subtotal,
    CONCAT('$', FORMAT(new_tax, 2)) as new_tax,
    CONCAT('$', FORMAT(new_subtotal + new_tax + COALESCE(tip, 0), 2)) as new_total,
    CONCAT('$', FORMAT((new_subtotal + new_tax + COALESCE(tip, 0)) - old_total, 2)) as difference
FROM order_recalc
WHERE ABS((new_subtotal + new_tax + COALESCE(tip, 0)) - old_total) > 0.01
ORDER BY order_id
LIMIT 20;

-- UNCOMMENT THE FOLLOWING LINES TO APPLY THE CHANGES:
-- WARNING: This will modify order totals!

/*
-- Update orders with correct calculations
UPDATE orders o
INNER JOIN order_recalc oc ON o.id = oc.order_id
SET
    o.subtotal = oc.new_subtotal,
    o.tax_amount = oc.new_tax,
    o.total_amount = oc.new_subtotal + oc.new_tax + COALESCE(oc.tip, 0)
WHERE ABS((oc.new_subtotal + oc.new_tax + COALESCE(oc.tip, 0)) - oc.old_total) > 0.01;

-- Recompute dining session totals
UPDATE dining_sessions ds
SET
    ds.subtotal = (
        SELECT COALESCE(SUM(o.subtotal), 0)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ),
    ds.tax_amount = (
        SELECT COALESCE(SUM(o.tax_amount), 0)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ),
    ds.total_amount = (
        SELECT COALESCE(SUM(o.total_amount), 0)
        FROM orders o
        WHERE o.session_id = ds.id AND o.workflow_status != 'cancelled'
    ) + COALESCE(ds.tip_amount, 0);

SELECT CONCAT('✅ Updated ', ROW_COUNT(), ' orders') as result;
*/

-- Clean up
DROP TEMPORARY TABLE IF EXISTS order_recalc;
