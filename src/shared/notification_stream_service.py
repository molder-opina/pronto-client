"""
Notification Stream Service - Send role-based notifications via Redis streams.

Notifications are sent to Redis streams and consumed by SSE endpoints.
Notifications are auto-removed from streams by maxlen configuration.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Stream name for notifications
REDIS_NOTIFICATIONS_STREAM = os.getenv("REDIS_NOTIFICATIONS_STREAM", "pronto:notifications:stream")
REDIS_NOTIFICATIONS_STREAM_MAXLEN = int(os.getenv("REDIS_NOTIFICATIONS_STREAM_MAXLEN", "1000"))


def _get_redis_client():
    """Get Redis client instance."""
    try:
        from shared.socketio_manager import _get_client

        return _get_client()
    except Exception as e:
        logger.warning(f"Error getting Redis client: {e}")
        return None


def _serialize_value(value: Any) -> Any:
    """Serialize datetime and other complex types to JSON-serializable format."""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return value


def send_notification(
    notification_type: str,
    recipient_role: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: str = "normal",
) -> bool:
    """
    Send a notification to a specific role via Redis stream.

    Args:
        notification_type: Type of notification (new_order, awaiting_payment, etc.)
        recipient_role: Role that receives the notification (waiter, chef, cashier, admin)
        title: Notification title
        message: Notification message
        data: Additional data payload
        priority: Priority level (low, normal, high)

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        client = _get_redis_client()
        if not client:
            logger.warning("Redis client not available, cannot send notification")
            return False

        # Build notification payload
        payload = {
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "data": data or {},
            "priority": priority,
            "recipient_role": recipient_role,
            "timestamp": _serialize_value(_timestamp()),
        }

        # Add to Redis stream
        event_type = f"notification:{recipient_role}"
        client.xadd(
            REDIS_NOTIFICATIONS_STREAM,
            {
                "type": event_type,
                "payload": str(payload),
                "timestamp": _serialize_value(_timestamp()),
            },
            maxlen=REDIS_NOTIFICATIONS_STREAM_MAXLEN,
            approximate=True,
        )

        logger.debug(f"Sent notification: {event_type} - {title} to {recipient_role}")
        return True

    except Exception as e:
        logger.error(f"Error sending notification to {recipient_role}: {e}")
        return False


def notify_waiters(
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: str = "normal",
) -> bool:
    """Send notification to all waiters."""
    return send_notification(notification_type, "waiter", title, message, data, priority)


def notify_chefs(
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: str = "normal",
) -> bool:
    """Send notification to all chefs."""
    return send_notification(notification_type, "chef", title, message, data, priority)


def notify_cashiers(
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: str = "normal",
) -> bool:
    """Send notification to all cashiers."""
    return send_notification(notification_type, "cashier", title, message, data, priority)


def notify_admins(
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: str = "normal",
) -> bool:
    """Send notification to all admins."""
    return send_notification(notification_type, "admin", title, message, data, priority)


def _timestamp() -> str:
    """Get current timestamp as string."""
    import time

    return str(time.time())
