"""
Notifications endpoints for clients API.
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, jsonify, request, session

notifications_bp = Blueprint("client_notifications", __name__)


@notifications_bp.get("/notifications")
def get_notifications():
    """Get unread notifications for the current user."""
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import Notification

    session.get("dining_session_id") or request.args.get("session_id")
    recipient_type = request.args.get("recipient_type", "customer")

    with get_session() as db_session:
        query = (
            select(Notification)
            .where(Notification.recipient_type == recipient_type, Notification.status == "unread")
            .order_by(Notification.created_at.desc())
            .limit(50)
        )

        notifications = db_session.execute(query).scalars().all()

        return jsonify(
            {
                "notifications": [
                    {
                        "id": n.id,
                        "type": n.notification_type,
                        "title": n.title,
                        "message": n.message,
                        "priority": n.priority,
                        "created_at": n.created_at.isoformat(),
                    }
                    for n in notifications
                ]
            }
        ), HTTPStatus.OK


@notifications_bp.post("/notifications/<int:notification_id>/read")
def mark_notification_read(notification_id: int):
    """Mark a notification as read."""
    from shared.db import get_session
    from shared.models import Notification

    with get_session() as db_session:
        notification = db_session.get(Notification, notification_id)
        if notification:
            notification.status = "read"
            notification.read_at = datetime.utcnow()
            db_session.commit()
            return jsonify({"status": "ok"}), HTTPStatus.OK

        return jsonify({"error": "Notification not found"}), HTTPStatus.NOT_FOUND
