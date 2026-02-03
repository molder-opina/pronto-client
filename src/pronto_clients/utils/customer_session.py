"""
Helpers for client-side session state with Redis-backed PII storage.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from flask import current_app

CUSTOMER_REF_TTL_SECONDS = int(os.getenv("CUSTOMER_REF_TTL_SECONDS", "3600"))
CUSTOMER_REF_PREFIX = "pronto:client:customer_ref:"
ALLOWED_SESSION_KEYS = {"dining_session_id", "customer_ref"}


def validate_session_key(key: str) -> bool:
    return key in ALLOWED_SESSION_KEYS


def set_session_key(session, key: str, value: Any) -> bool:
    if not validate_session_key(key):
        current_app.logger.warning(
            f"Intento de asignar clave no permitida a session: {key}"
        )
        return False
    session[key] = value
    return True


def _get_redis_client():
    try:
        from pronto_shared.socketio_manager import _get_client

        return _get_client()
    except Exception as exc:
        current_app.logger.warning(f"Redis client unavailable for customer_ref: {exc}")
        return None


def store_customer_ref(data: dict[str, Any]) -> str | None:
    client = _get_redis_client()
    if not client:
        return None

    customer_ref = str(uuid.uuid4())
    payload = json.dumps(data, ensure_ascii=False)
    try:
        client.setex(
            f"{CUSTOMER_REF_PREFIX}{customer_ref}", CUSTOMER_REF_TTL_SECONDS, payload
        )
        return customer_ref
    except Exception as exc:
        current_app.logger.error(f"Failed to store customer_ref in Redis: {exc}")
        return None


def clear_customer_ref(customer_ref: str) -> None:
    client = _get_redis_client()
    if not client:
        return
    try:
        client.delete(f"{CUSTOMER_REF_PREFIX}{customer_ref}")
    except Exception as exc:
        current_app.logger.warning(f"Failed to delete customer_ref in Redis: {exc}")
