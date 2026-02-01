"""
Notifications API - SSE streaming for real-time notifications by role.
Notifications are consumed from Redis streams and auto-removed.
"""

from collections.abc import Generator
from http import HTTPStatus

from flask import Blueprint, Response, jsonify, request, stream_with_context

from employees_app.decorators import admin_required
from shared.jwt_middleware import (
    get_active_scope,
    get_current_user,
    get_employee_id,
    get_employee_role,
    jwt_required,
)
from shared.db import get_session
from shared.models import Notification
from shared.socketio_manager import read_events_from_stream

notifications_bp = Blueprint("notifications", __name__)


@jwt_required
@notifications_bp.get("/notifications/stream")
def notifications_stream():
    """
    SSE endpoint for real-time notifications based on user role.

    Only shows NEW notifications after connection (not all accumulated ones).
    Notifications are consumed/removed from Redis stream by maxlen configuration.
    """
    import json
    import logging
    import os
    import time

    from shared.socketio_manager import _get_client

    user = get_current_user()
    employee_role = get_employee_role() or ""
    active_scope = get_active_scope() or ""

    # Map roles to notification event types
    role_event_types = {
        "waiter": ["notification:waiter"],
        "chef": ["notification:chef"],
        "cashier": ["notification:cashier"],
        "admin": ["notification:admin"],
        "super_admin": ["notification:admin"],
        "system": ["notification:admin"],
    }

    # Get notification types for this user's role
    notification_types = role_event_types.get(employee_role, [])

    # Also check by active_scope (waiter, chef, cashier, admin)
    if not notification_types and active_scope:
        scope_event_types = {
            "waiter": ["notification:waiter"],
            "chef": ["notification:chef"],
            "cashier": ["notification:cashier"],
            "admin": ["notification:admin"],
            "system": ["notification:admin"],
        }
        notification_types = scope_event_types.get(active_scope, [])

    if not notification_types:
        return jsonify({"error": "No notifications for this role"}), HTTPStatus.BAD_REQUEST

    # Get notification stream name
    notifications_stream = os.getenv("REDIS_NOTIFICATIONS_STREAM", "pronto:notifications:stream")

    def generate() -> Generator[str, None, None]:
        """Generate SSE events for notifications."""
        last_id = "0-0"
        poll_interval = 1.0  # seconds

        while True:
            try:
                client = _get_client()
                if not client:
                    time.sleep(poll_interval)
                    continue

                # Read events from notifications stream
                response = client.xread({notifications_stream: last_id}, count=10)

                events = []
                for _, entries in response:
                    for entry_id, data in entries:
                        last_id = entry_id
                        event_type = data.get("type", "")
                        payload_raw = data.get("payload", "{}")

                        # Parse payload
                        try:
                            payload = (
                                json.loads(payload_raw) if isinstance(payload_raw, str) else {}
                            )
                        except json.JSONDecodeError:
                            payload = {}

                        # Check if this event is for this user's role
                        if event_type in notification_types:
                            events.append(
                                {
                                    "id": entry_id,
                                    "type": payload.get("notification_type", "notification"),
                                    "title": payload.get("title", ""),
                                    "message": payload.get("message", ""),
                                    "data": payload.get("data", {}),
                                    "priority": payload.get("priority", "normal"),
                                    "timestamp": payload.get("timestamp", ""),
                                }
                            )

                # Send each notification as SSE event
                for notification in events:
                    sse_data = json.dumps(notification)
                    yield f"data: {sse_data}\n\n"

                    # Events are auto-removed from Redis stream by maxlen configuration

            except GeneratorExit:
                break
            except Exception as e:
                logging.getLogger(__name__).error(f"Error in notifications stream: {e}")

            # Wait before next poll
            time.sleep(poll_interval)

    # Return SSE stream
    response = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable buffering for Nginx
        },
    )
    return response


@notifications_bp.post("/notifications/clear")
@admin_required
def clear_notifications():
    """
    Elimina todas las notificaciones.

    Solo administradores/system pueden ejecutar esta acción.
    """
    try:
        with get_session() as session:
            deleted = session.query(Notification).delete()
            session.commit()
            return jsonify(
                {"message": "Notificaciones eliminadas", "deleted": deleted}
            ), HTTPStatus.OK
    except Exception as exc:
        return jsonify(
            {"error": f"No se pudieron eliminar las notificaciones: {exc}"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@notifications_bp.post("/notifications/call-admin")
def call_admin():
    """
    Trigger a generic admin call notification via notification stream.
    """
    from flask import request

    from shared.notification_stream_service import notify_admins

    try:
        data = request.get_json() or {}
        message = data.get("message")

        sender_id = get_employee_id()
        user = get_current_user()
        sender_name = user.get("employee_name", "Staff") if user else "Staff"
        sender_role = user.get("employee_role", "unknown") if user else "unknown"

        if not sender_id:
            return jsonify({"error": "Unauthorized"}), HTTPStatus.UNAUTHORIZED

        # Send notification to admins via Redis stream
        title = f"Llamada de {sender_name}"
        msg = f"{sender_role} solicita atención"
        if message:
            msg += f": {message}"

        notify_admins(
            "admin_call",
            title,
            msg,
            {"sender_id": sender_id, "sender_name": sender_name, "sender_role": sender_role},
            priority="high",
        )

        return jsonify({"message": "Admin notificado"}), HTTPStatus.OK
    except Exception as exc:
        return jsonify({"error": f"Failed to call admin: {exc}"}), HTTPStatus.INTERNAL_SERVER_ERROR
