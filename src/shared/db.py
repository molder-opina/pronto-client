"""
Database helpers shared by the pronto services.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import AppConfig

_engine = None
_session_factory: sessionmaker | None = None
_scoped_session: scoped_session | None = None


def init_engine(config: AppConfig):
    """
    Initialize a SQLAlchemy engine and session factory using the given config.

    The engine is stored as a module-level singleton so that multiple blueprints
    can safely reuse the same connection pool inside a container.
    """
    global _engine, _session_factory, _scoped_session

    if _engine is None:
        database_url = os.getenv("DATABASE_URL") or config.sqlalchemy_uri
        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "future": True,
            "pool_size": 10,  # Número de conexiones permanentes en el pool
            "max_overflow": 20,  # Conexiones adicionales permitidas cuando el pool está lleno
            "pool_recycle": 3600,  # Recicla conexiones cada hora para evitar timeouts
        }

        if database_url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                    "pool_pre_ping": False,
                }
            )

        _engine = create_engine(
            database_url,
            **engine_kwargs,
        )

        # Habilitar logging de queries lentas (más de 1 segundo)
        @event.listens_for(_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault("query_start_time", []).append(time.time())

        @event.listens_for(_engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total = time.time() - conn.info["query_start_time"].pop(-1)
            if total > 1.0:  # Log queries que toman más de 1 segundo
                logger.warning(f"Slow query detected ({total:.2f}s): {statement[:200]}...")

        _session_factory = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        _scoped_session = scoped_session(_session_factory)

    return _engine


logger = logging.getLogger(__name__)


def init_db(metadata) -> None:
    """
    Ensure all tables declared on the provided metadata exist in the database.

    NOTE: create_all() is disabled because tables are managed via SQL migrations.
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine first.")

    # Enabled: Create tables automatically for local development
    try:
        metadata.create_all(_engine)
        logger.info("Database schema created successfully")
    except OperationalError as exc:
        # PostgreSQL handles CREATE TABLE IF NOT EXISTS correctly
        logger.warning("Schema creation warning: %s", exc)

    # Run schema migrations for new columns
    _ensure_employee_preferences_column()


def _ensure_employee_preferences_column() -> None:
    """
    Ensure the pronto_employees.preferences column exists (PostgreSQL).
    This handles cases where the column was added after initial deployment.
    """
    if _engine is None:
        return
    try:
        from sqlalchemy import text

        with _engine.connect() as conn:
            # Check if column exists (PostgreSQL requires schema specification)
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'pronto_employees' "
                    "AND column_name = 'preferences'"
                )
            )
            exists = result.scalar() > 0

            if not exists:
                logger.info("Adding 'preferences' column to pronto_employees table")
                try:
                    # PostgreSQL allows defaults on TEXT columns
                    conn.execute(text("ALTER TABLE pronto_employees ADD COLUMN preferences TEXT"))
                    conn.execute(
                        text(
                            "UPDATE pronto_employees SET preferences = '{}' WHERE preferences IS NULL"
                        )
                    )
                    conn.commit()
                    logger.info("Successfully added 'preferences' column")
                except Exception:
                    conn.rollback()
                    raise
    except Exception as e:
        logger.warning(f"Could not ensure preferences column: {e}")


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Provide a transactional scope around a series of operations.

    Yields a session and automatically rolls back when an exception occurs. It
    commits by default and always ensures the session is removed from the scoped
    registry afterwards.
    """
    if _scoped_session is None:
        raise RuntimeError("Session factory unavailable. Call init_engine first.")

    session: Session = _scoped_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _scoped_session.remove()
