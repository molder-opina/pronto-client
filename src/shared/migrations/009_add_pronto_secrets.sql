-- Created: 2026-01-12
-- Description: Add secrets table for env sync

USE pronto;

CREATE TABLE IF NOT EXISTS pronto_secrets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    secret_key VARCHAR(120) NOT NULL,
    secret_value TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY ix_secret_key (secret_key)
);

INSERT INTO schema_migrations (version, applied_at)
VALUES ('009_add_pronto_secrets', NOW())
ON DUPLICATE KEY UPDATE applied_at = NOW();
