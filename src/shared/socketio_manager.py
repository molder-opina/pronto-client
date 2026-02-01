"""
Redis-backed real-time state and event helpers.

This module replaces the previous Flask-SocketIO layer and centralises all
real-time notifications in Redis. Each helper stores structured state using the
`pronto:{entity}:{id}` key pattern and publishes JSON events on
`REDIS_EVENTS_CHANNEL` (default: `pronto:events`).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from threading import Lock
from typing import Any

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - optional dependency
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        """Fallback Redis error when redis-py is unavailable."""

        pass


logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_EVENTS_CHANNEL = os.getenv("REDIS_EVENTS_CHANNEL", "pronto:events")
REDIS_EVENTS_STREAM = os.getenv("REDIS_EVENTS_STREAM", "pronto:events:stream")
REDIS_EVENTS_STREAM_MAXLEN = int(os.getenv("REDIS_EVENTS_STREAM_MAXLEN", "1000"))
REDIS_EVENTS_FETCH_LIMIT = int(os.getenv("REDIS_EVENTS_FETCH_LIMIT", "100"))

STATE_TTLS = {
    "orders": int(os.getenv("REDIS_ORDERS_TTL", "86400")),  # 24h
    "sessions": int(os.getenv("REDIS_SESSIONS_TTL", "14400")),  # 4h
    "tables": int(os.getenv("REDIS_TABLES_TTL", "14400")),  # 4h
    "notifications": int(os.getenv("REDIS_NOTIFICATIONS_TTL", "3600")),  # 1h
}

_client: Redis | None = None
_client_lock = Lock()


def _serialize_value(value: Any) -> Any:
    """Ensure payloads can be JSON serialised."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return value


def _get_client() -> Redis | None:
    """Return a shared Redis client instance."""
    global _client  # noqa: PLW0603 - module level cache
    if Redis is None:
        logger.warning("redis package not installed; real-time features disabled during runtime.")
        return None
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        try:
            _client = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD or None,
                decode_responses=True,
            )
        except Exception as exc:  # pragma: no cover - connection errors
            logger.warning("Unable to initialise Redis client: %s", exc)
            return None

    return _client


def _state_key(bucket: str, identifier: Any) -> str:
    return f"pronto:{bucket}:{identifier}"


def _store_state(
    bucket: str, identifier: Any, payload: dict[str, Any], ttl: int | None = None
) -> None:
    """Serialize and persist payload under the recommended Redis key structure."""
    client = _get_client()
    if not client:
        return

    key = _state_key(bucket, identifier)
    try:
        encoded = json.dumps(payload, default=_serialize_value)
        client.set(key, encoded)
        effective_ttl = ttl if ttl is not None else STATE_TTLS.get(bucket)
        if effective_ttl:
            client.expire(key, int(effective_ttl))
    except RedisError as exc:
        logger.warning("Failed to write redis state %s: %s", key, exc)


def _publish_event(event_type: str, payload: dict[str, Any], channel: str | None = None) -> None:
    """Publish a JSON event to the configured channel."""
    client = _get_client()
    if not client:
        return

    message = {
        "type": event_type,
        "payload": payload,
        "timestamp": payload.get("timestamp") or datetime.now(UTC).isoformat(),
    }

    try:
        client.publish(
            channel or REDIS_EVENTS_CHANNEL, json.dumps(message, default=_serialize_value)
        )
        _append_event_to_stream(message, client)
    except RedisError as exc:
        logger.warning("Failed to publish redis event %s: %s", event_type, exc)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _append_event_to_stream(message: dict[str, Any], client: Redis | None = None) -> None:
    """
    Persist the event in a Redis stream so HTTP clients can poll for updates.
    """
    if not REDIS_EVENTS_STREAM:
        return

    redis_client = client or _get_client()
    if not redis_client:
        return

    try:
        redis_client.xadd(
            REDIS_EVENTS_STREAM,
            {
                "type": message.get("type", "unknown"),
                "payload": json.dumps(message.get("payload", {}), default=_serialize_value),
                "timestamp": message.get("timestamp") or _timestamp(),
            },
            maxlen=REDIS_EVENTS_STREAM_MAXLEN,
            approximate=True,
        )
    except RedisError as exc:
        logger.warning("Failed to append redis stream event %s: %s", message.get("type"), exc)


def read_events_from_stream(
    after_id: str = "0-0", count: int | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """
    Read events stored in the Redis stream after the provided ID.

    Returns a tuple of (last_id, events) where `last_id` is the latest stream
    ID processed. Callers can pass that ID again to only retrieve new events.
    """
    if not REDIS_EVENTS_STREAM:
        return after_id, []

    client = _get_client()
    if not client:
        return after_id, []

    stream_id = after_id or "0-0"
    fetch_count = count or REDIS_EVENTS_FETCH_LIMIT
    fetch_count = max(1, min(fetch_count, 500))

    try:
        response = client.xread({REDIS_EVENTS_STREAM: stream_id}, count=fetch_count)
    except RedisError as exc:
        logger.warning("Failed to read redis stream %s: %s", REDIS_EVENTS_STREAM, exc)
        return after_id, []

    events: list[dict[str, Any]] = []
    last_id = after_id

    for _, entries in response:
        for entry_id, data in entries:
            last_id = entry_id
            payload_raw = data.get("payload")
            payload: dict[str, Any]
            if isinstance(payload_raw, str):
                try:
                    payload = json.loads(payload_raw)
                except json.JSONDecodeError:
                    payload = {"raw": payload_raw}
            else:
                payload = payload_raw or {}

            events.append(
                {
                    "id": entry_id,
                    "type": data.get("type"),
                    "timestamp": data.get("timestamp"),
                    "payload": payload,
                }
            )

    return last_id, events


def emit_order_status_change(
    order_id: int,
    status: str,
    session_id: int,
    table_number: str | None = None,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Store the current order status and broadcast the change via Redis.
    """
    try:
        data = {
            "order_id": order_id,
            "status": status,
            "session_id": session_id,
            "table_number": table_number,
            "timestamp": _timestamp(),
        }
        if payload:
            data.update(payload)

        _store_state("orders", order_id, data)
        _publish_event("orders.status_changed", data)

        if session_id:
            _store_state(
                "sessions",
                session_id,
                {"session_id": session_id, "last_order": data, "updated_at": data["timestamp"]},
            )

        if table_number:
            _store_state(
                "tables",
                table_number,
                {"table_number": table_number, "last_order": data, "updated_at": data["timestamp"]},
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process order status change event: %s", exc)


def emit_new_order(
    order_id: int,
    session_id: int,
    table_number: str | None = None,
    order_data: dict[str, Any] | None = None,
) -> None:
    """
    Persist and broadcast a new order event.
    """
    try:
        data = {
            "order_id": order_id,
            "session_id": session_id,
            "table_number": table_number,
            "order_data": order_data or {},
            "timestamp": _timestamp(),
        }

        _store_state("orders", order_id, data)
        _publish_event("orders.created", data)

        if session_id:
            _store_state(
                "sessions",
                session_id,
                {
                    "session_id": session_id,
                    "last_order_id": order_id,
                    "order_data": order_data or {},
                    "updated_at": data["timestamp"],
                },
            )

        if table_number:
            _store_state(
                "tables",
                table_number,
                {
                    "table_number": table_number,
                    "active_session_id": session_id,
                    "last_order_id": order_id,
                    "updated_at": data["timestamp"],
                },
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process new order event: %s", exc)


def emit_session_status_change(
    session_id: int,
    status: str,
    table_number: str | None = None,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Emit a session status change event to notify all employees.
    This is used when session status changes (e.g., open -> awaiting_tip -> awaiting_payment -> closed).
    """
    try:
        data = {
            "session_id": session_id,
            "status": status,
            "table_number": table_number,
            "timestamp": _timestamp(),
        }
        if payload:
            data.update(payload)

        _store_state(
            "sessions",
            session_id,
            {"session_id": session_id, "status": status, "updated_at": data["timestamp"]},
        )
        _publish_event("sessions.status_changed", data)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to emit session status change: %s", exc)


def emit_waiter_call(
    call_id: int,
    session_id: int,
    table_number: str,
    status: str,
    call_type: str | None = None,
    order_numbers: list[int] | None = None,
    *,
    waiter_id: int | None = None,
    waiter_name: str | None = None,
    created_at: datetime | None = None,
) -> None:
    """
    Persist waiter call state and broadcast the notification.
    """
    try:
        data = {
            "call_id": call_id,
            "session_id": session_id,
            "table_number": table_number,
            "status": status,
            "call_type": call_type,
            "order_numbers": order_numbers or [],
            "waiter_id": waiter_id,
            "waiter_name": waiter_name,
            "created_at": created_at.isoformat() if created_at else None,
            "timestamp": _timestamp(),
        }

        _store_state(
            "tables",
            table_number,
            {"table_number": table_number, "active_call": data, "updated_at": data["timestamp"]},
        )
        _publish_event("customers.waiter_call", data)

        notification_target = str(waiter_id) if waiter_id else "broadcast"
        _store_state("notifications", notification_target, data, ttl=STATE_TTLS["notifications"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process waiter call event: %s", exc)


def emit_supervisor_call(
    employee_id: int,
    employee_name: str,
    table_number: str | None = None,
    order_id: int | None = None,
) -> None:
    """
    Broadcast a supervisor request event.
    """
    try:
        data = {
            "waiter_id": employee_id,
            "waiter_name": employee_name,
            "table_number": table_number,
            "order_id": order_id,
            "timestamp": _timestamp(),
        }

        _publish_event("staff.supervisor_call", data)
        notification_target = str(employee_id)
        _store_state("notifications", notification_target, data, ttl=STATE_TTLS["notifications"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process supervisor call event: %s", exc)


def emit_custom_event(event: str, data: dict[str, Any], room: str | None = None) -> None:
    """
    Helper kept for backwards compatibility. `room` is mapped to the Redis key namespace.
    """
    try:
        payload = dict(data)
        payload["room"] = room
        payload["timestamp"] = payload.get("timestamp") or _timestamp()
        _publish_event(event, payload)
        if room:
            _store_state("notifications", room, payload, ttl=STATE_TTLS["notifications"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to emit custom redis event %s: %s", event, exc)


__all__ = [
    "emit_admin_call",
    "emit_waiter_call",
    "read_events_from_stream",
]


def emit_admin_call(
    sender_id: int,
    sender_name: str,
    sender_role: str,
    message: str | None = None,
) -> None:
    """
    Broadcast a generic admin call event from any staff member.
    """
    try:
        data = {
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_role": sender_role,
            "message": message or "Solicita asistencia del administrador",
            "timestamp": _timestamp(),
        }

        _publish_event("staff.admin_call", data)
        # Store for admin notifications
        _store_state("notifications", "admin", data, ttl=STATE_TTLS["notifications"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process admin call event: %s", exc)
