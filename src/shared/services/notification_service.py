"""
Notification service for real-time updates using Server-Sent Events (SSE).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass


@dataclass
class Notification:
    """Notification message."""

    id: str
    type: str
    title: str
    message: str
    data: dict | None = None
    priority: str = "normal"  # low, normal, high
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self):
        """Convert to dictionary."""
        result = asdict(self)
        result["timestamp"] = int(self.timestamp * 1000)  # milliseconds
        return result

    def to_sse_format(self) -> str:
        """Convert to SSE format."""
        data = json.dumps(self.to_dict())
        return f"data: {data}\n\n"


class NotificationManager:
    """
    Manages real-time notifications using an in-memory queue.
    In production, consider using Redis for multi-process support.
    """

    def __init__(self):
        # Store notifications by channel
        # channel -> list of notifications
        self._notifications: dict[str, list[Notification]] = defaultdict(list)
        self._max_notifications_per_channel = 100

    def send(
        self,
        channel: str,
        notification_type: str,
        title: str,
        message: str,
        data: dict | None = None,
        priority: str = "normal",
    ) -> Notification:
        """
        Send a notification to a specific channel.

        Args:
            channel: Channel to send to (e.g., "waiter:1", "all_waiters", "session:123")
            notification_type: Type of notification (new_order, order_ready, payment, etc.)
            title: Notification title
            message: Notification message
            data: Additional data
            priority: Priority level (low, normal, high)

        Returns:
            The created notification
        """
        notification = Notification(
            id=f"{channel}:{int(time.time() * 1000)}",
            type=notification_type,
            title=title,
            message=message,
            data=data or {},
            priority=priority,
        )

        # Add to channel queue
        self._notifications[channel].append(notification)

        # Limit queue size
        if len(self._notifications[channel]) > self._max_notifications_per_channel:
            self._notifications[channel] = self._notifications[channel][
                -self._max_notifications_per_channel :
            ]

        return notification

    def get_notifications(self, channel: str, since: float | None = None) -> list[Notification]:
        """
        Get notifications for a channel since a specific timestamp.

        Args:
            channel: Channel to get notifications from
            since: Timestamp to get notifications since (epoch seconds)

        Returns:
            List of notifications
        """
        notifications = self._notifications.get(channel, [])

        if since is not None:
            notifications = [n for n in notifications if n.timestamp > since]

        return notifications

    def clear_channel(self, channel: str):
        """Clear all notifications for a channel."""
        if channel in self._notifications:
            del self._notifications[channel]

    def broadcast_to_waiters(
        self,
        notification_type: str,
        title: str,
        message: str,
        data: dict | None = None,
        priority: str = "normal",
    ) -> Notification:
        """Broadcast a notification to all waiters."""
        return self.send("all_waiters", notification_type, title, message, data, priority)

    def broadcast_to_chefs(
        self,
        notification_type: str,
        title: str,
        message: str,
        data: dict | None = None,
        priority: str = "normal",
    ) -> Notification:
        """Broadcast a notification to all chefs."""
        return self.send("all_chefs", notification_type, title, message, data, priority)

    def notify_session(
        self,
        session_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: dict | None = None,
        priority: str = "normal",
    ) -> Notification:
        """Send notification to a specific dining session (customer)."""
        return self.send(f"session:{session_id}", notification_type, title, message, data, priority)


# Global notification manager instance
_notification_manager = NotificationManager()


def get_notification_manager() -> NotificationManager:
    """Get the global notification manager instance."""
    return _notification_manager
