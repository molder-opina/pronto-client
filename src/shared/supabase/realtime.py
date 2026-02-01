"""
Supabase Realtime manager - reemplaza socketio_manager.py

Este módulo maneja eventos en tiempo real usando Supabase Realtime en lugar de Redis.
Con Supabase, los eventos se propagan automáticamente cuando se hacen cambios en la base de datos.
"""

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class RealtimeManager:
    """
    Maneja eventos en tiempo real usando PostgreSQL.

    Persiste eventos en la base de datos para que los clientes
    puedan consumirlos mediante polling o streams.
    """

    @staticmethod
    def _serialize_value(value: Any) -> Any:
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

    @classmethod
    def _persist_event(cls, event_type: str, payload: dict[str, Any] | None) -> None:
        # Publish to Redis for real-time WebSocket notifications
        try:
            from shared.socketio_manager import (
                _append_event_to_stream,
                _publish_event,
            )

            if payload:
                # Publish to Redis pub/sub channel and stream
                _publish_event(event_type, payload)
                logger.debug(f"Published event '{event_type}' to Redis")
        except ImportError:
            logger.warning("socketio_manager not available, skipping Redis publish")
        except Exception as redis_error:
            logger.warning(f"Error publishing to Redis (continuing): {redis_error}")

        # Also persist to PostgreSQL as backup for polling clients
        try:
            from shared.db import get_session
            from shared.models import RealtimeEvent

            payload_json = None
            if payload:
                payload_json = json.dumps(payload, default=cls._serialize_value)

            with get_session() as session:
                session.add(RealtimeEvent(event_type=event_type, payload=payload_json))
        except Exception as e:
            logger.error(f"Error persisting realtime event '{event_type}': {e}")

    @classmethod
    def emit_order_status_change(
        cls,
        order_id: int,
        status: str,
        session_id: int | None = None,
        table_number: str | None = None,
        **extra_data,
    ) -> None:
        """
        Emite un evento de cambio de estado de pedido.

        Con Supabase Realtime, el UPDATE en la tabla 'orders'
        ya dispara automáticamente el evento a clientes suscritos.
        Este método solo registra el evento para logging.
        """
        payload = {
            "order_id": order_id,
            "status": status,
            "session_id": session_id,
            "table_number": table_number,
            **extra_data,
        }
        cls._persist_event("orders.status_changed", payload)

    @classmethod
    def emit_new_order(
        cls, order_id: int, session_id: int, table_number: str | None = None, **extra_data
    ) -> None:
        """
        Emite un evento de nueva orden.

        El INSERT en la tabla 'orders' dispara Realtime automáticamente.
        """
        payload = {
            "order_id": order_id,
            "session_id": session_id,
            "table_number": table_number,
            **extra_data,
        }
        cls._persist_event("orders.new", payload)

    @classmethod
    def emit_session_status_change(cls, session_id: int, status: str, **extra_data) -> None:
        """
        Emite un evento de cambio de estado de sesión.

        El UPDATE en la tabla 'dining_sessions' dispara Realtime automáticamente.
        """
        payload = {"session_id": session_id, "status": status, **extra_data}
        cls._persist_event("sessions.status_changed", payload)

    @classmethod
    def emit_waiter_call(
        cls, session_id: int, table_number: str, call_id: int | None = None, **extra_data
    ) -> None:
        """
        Emite un evento de llamada de mesero.

        El INSERT en la tabla 'waiter_calls' dispara Realtime automáticamente.
        """
        payload = {
            "session_id": session_id,
            "table_number": table_number,
            "call_id": call_id,
            **extra_data,
        }
        cls._persist_event("waiter.call", payload)

    @classmethod
    def emit_supervisor_call(
        cls, employee_id: int, employee_name: str, reason: str | None = None, **extra_data
    ) -> None:
        """
        Emite un evento de llamada de supervisor.

        Para eventos que no corresponden a cambios en tablas principales,
        se usa la tabla 'custom_events'.
        """
        payload = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "reason": reason,
            **extra_data,
        }
        cls._persist_event("supervisor.call", payload)

    @classmethod
    def emit_custom_event(cls, event_type: str, payload: dict[str, Any]) -> None:
        """
        Emite un evento personalizado usando la tabla custom_events.

        Args:
            event_type: Tipo de evento (ej: "table_assigned", "order_modified")
            payload: Datos del evento
        """
        cls._persist_event(event_type, {"payload": payload})

    @classmethod
    def set_state(cls, bucket: str, identifier: str, data: dict[str, Any]) -> None:
        """
        Almacena estado temporal en Redis.
        """
        try:
            from shared.socketio_manager import _store_state

            # Usar un TTL por defecto de 1 hora para estado temporal
            _store_state(bucket, identifier, data, ttl=3600)
        except ImportError:
            logger.warning("socketio_manager not available, cannot store state in Redis")
        except Exception as e:
            logger.error(f"Error restoring state to Redis: {e}")

    @classmethod
    def get_state(cls, bucket: str, identifier: str) -> dict[str, Any] | None:
        """
        Recupera estado temporal de Redis.
        """
        try:
            import json

            from shared.socketio_manager import _get_client, _state_key

            client = _get_client()
            if not client:
                return None

            key = _state_key(bucket, identifier)
            data = client.get(key)

            if data:
                return json.loads(data)
            return None
        except ImportError:
            logger.warning("socketio_manager not available, cannot get state from Redis")
            return None
        except Exception as e:
            logger.error(f"Error getting state from Redis: {e}")
            return None

    @classmethod
    def read_events_from_stream(
        cls,
        after_id: str = "0-0",
        count: int | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Retorna eventos pendientes desde PostgreSQL y los elimina al consumirlos.
        """
        from sqlalchemy import delete, select

        from shared.db import get_session
        from shared.models import RealtimeEvent

        limit = max(1, min(count or 100, 500))
        try:
            last_id = 0
            if after_id and after_id != "0-0":
                try:
                    last_id = int(after_id.split("-", 1)[0])
                except ValueError:
                    last_id = 0

            with get_session() as session:
                rows = (
                    session.execute(
                        select(RealtimeEvent)
                        .where(RealtimeEvent.id > last_id)
                        .order_by(RealtimeEvent.id)
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )

                if not rows:
                    return after_id, []

                ids = [row.id for row in rows]
                events: list[dict[str, Any]] = []
                for row in rows:
                    payload: dict[str, Any] = {}
                    if row.payload:
                        try:
                            payload = json.loads(row.payload)
                        except json.JSONDecodeError:
                            payload = {"raw": row.payload}

                    events.append(
                        {
                            "id": str(row.id),
                            "type": row.event_type,
                            "timestamp": row.created_at.isoformat() if row.created_at else None,
                            "payload": payload,
                        }
                    )

                session.execute(delete(RealtimeEvent).where(RealtimeEvent.id.in_(ids)))

            return str(ids[-1]), events
        except Exception as e:
            logger.error(f"Error reading realtime events: {e}")
            return after_id, []


# Alias para compatibilidad con código existente que importa desde socketio_manager
# Alias para compatibilidad con código existente que importa desde socketio_manager
emit_order_status_change = RealtimeManager.emit_order_status_change
emit_new_order = RealtimeManager.emit_new_order
emit_session_status_change = RealtimeManager.emit_session_status_change
emit_waiter_call = RealtimeManager.emit_waiter_call
emit_supervisor_call = RealtimeManager.emit_supervisor_call
emit_custom_event = RealtimeManager.emit_custom_event
set_state = RealtimeManager.set_state
get_state = RealtimeManager.get_state
read_events_from_stream = RealtimeManager.read_events_from_stream


logger.info("Supabase Realtime module loaded successfully")
