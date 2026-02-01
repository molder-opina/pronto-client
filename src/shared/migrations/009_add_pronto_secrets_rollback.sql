-- Created: 2026-01-12
-- Description: Rollback secrets table migration

USE pronto;

DROP TABLE IF EXISTS pronto_secrets;

DELETE FROM schema_migrations
WHERE version = '009_add_pronto_secrets';
