-- Unify session status: change 'billed' to 'paid'
-- This ensures we only have one paid status instead of two

UPDATE dining_sessions
SET status = 'paid'
WHERE status = 'billed';
