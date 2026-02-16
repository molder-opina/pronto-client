"""
Notifications endpoints for clients API.
Uses customer_ref from flask.session + Redis for authentication.
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, jsonify, request, session

from pronto_shared.services.customer_session_store import (
    customer_session_store,
    RedisUnavailableError,
)

notifications_bp = Blueprint("client_notifications", __name__)


def _get_authenticated_customer() -> dict | None:
    """Get authenticated customer from flask.session + Redis."""
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return None
    try:
        if customer_session_store.is_revoked(customer_ref):
            session.pop("customer_ref", None)
            return None
        return customer_session_store.get_customer(customer_ref)
    except RedisUnavailableError:
        return None


@notifications_bp.get("/notifications")
def get_notifications():
    """Get unread notifications for the current authenticated customer."""
    from sqlalchemy import select

    from pronto_shared.db import get_session as get_db_session
    from pronto_shared.models import Notification

    customer = _get_authenticated_customer()
    if not customer:
        return jsonify({"error": "Authentication required"}), HTTPStatus.UNAUTHORIZED

    customer_id = customer.get("customer_id")
    if not customer_id:
        return jsonify({"error": "Authentication required"}), HTTPStatus.UNAUTHORIZED

    with get_db_session() as db_session:
        query = (
            select(Notification)
            .where(
                Notification.recipient_type == "customer",
                Notification.recipient_id == customer_id,
                Notification.status == "unread",
            )
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
    """Mark a notification as read (requires auth + ownership check)."""
    from pronto_shared.db import get_session as get_db_session
    from pronto_shared.models import Notification

    customer = _get_authenticated_customer()
    if not customer:
        return jsonify({"error": "Authentication required"}), HTTPStatus.UNAUTHORIZED

    customer_id = customer.get("customer_id")

    with get_db_session() as db_session:
        notification = db_session.get(Notification, notification_id)
        if not notification:
            return jsonify({"error": "Notification not found"}), HTTPStatus.NOT_FOUND

        if notification.recipient_type != "customer" or str(notification.recipient_id) != str(customer_id):
            return jsonify({"error": "Notification not found"}), HTTPStatus.NOT_FOUND

        notification.status = "read"
        notification.read_at = datetime.utcnow()
        db_session.commit()
        return jsonify({"status": "ok"}), HTTPStatus.OK
