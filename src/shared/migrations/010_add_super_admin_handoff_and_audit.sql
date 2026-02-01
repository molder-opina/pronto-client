-- Migration: Add super_admin_handoff_tokens and audit_logs tables
-- Created: 2026-01-25
-- Purpose: Support super_admin reauth flow with one-time tokens and audit trail

-- Create super_admin_handoff_tokens table
CREATE TABLE IF NOT EXISTS super_admin_handoff_tokens (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    employee_id INTEGER NOT NULL REFERENCES pronto_employees(id) ON DELETE CASCADE,
    target_scope VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    ip_address VARCHAR(45),
    user_agent TEXT
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_handoff_token_hash ON super_admin_handoff_tokens(token_hash);
CREATE INDEX IF NOT EXISTS ix_handoff_expires_at ON super_admin_handoff_tokens(expires_at);
CREATE INDEX IF NOT EXISTS ix_handoff_employee_id ON super_admin_handoff_tokens(employee_id);

-- Create audit_logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES pronto_employees(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    scope_from VARCHAR(20),
    scope_to VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ip_address VARCHAR(45),
    user_agent TEXT,
    token_id INTEGER REFERENCES super_admin_handoff_tokens(id) ON DELETE SET NULL
);

-- Create indexes for audit queries
CREATE INDEX IF NOT EXISTS ix_audit_employee_id ON audit_logs(employee_id);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_token_id ON audit_logs(token_id);

-- Add comments for documentation
COMMENT ON TABLE super_admin_handoff_tokens IS 'One-time tokens for super_admin reauth flow (60s TTL)';
COMMENT ON TABLE audit_logs IS 'Security audit trail for authentication events';

COMMENT ON COLUMN super_admin_handoff_tokens.token_hash IS 'SHA-256 hash of token + pepper';
COMMENT ON COLUMN super_admin_handoff_tokens.target_scope IS 'Destination scope: waiter, chef, cashier, admin';
COMMENT ON COLUMN super_admin_handoff_tokens.used_at IS 'NULL = unused, NOT NULL = consumed (one-time)';

COMMENT ON COLUMN audit_logs.action IS 'Action type: reauth_token_generated, super_admin_handoff_login';
COMMENT ON COLUMN audit_logs.token_id IS 'Reference to handoff token (for correlation)';
