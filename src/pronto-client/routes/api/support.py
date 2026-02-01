"""
Support ticket endpoints for clients API.
"""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from clients_app.utils.input_sanitizer import (
    InputValidationError,
    sanitize_customer_name,
    sanitize_email,
    sanitize_support_description,
)
from pronto_shared.db import get_session
from pronto_shared.models import SupportTicket

support_bp = Blueprint("client_support", __name__)


@support_bp.post("/support-tickets")
def create_support_ticket():
    """Allow customers to report an issue to support."""
    payload = request.get_json(silent=True) or {}

    try:
        name = sanitize_customer_name(payload.get("name"))
        email = sanitize_email(payload.get("email"))
        description = sanitize_support_description(payload.get("description"))
    except InputValidationError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    page_url = (payload.get("page_url") or "").strip()
    if len(page_url) > 255:
        page_url = page_url[:255]

    channel = (payload.get("channel") or "client").strip().lower()[:32] or "client"
    user_agent = (request.headers.get("User-Agent") or "")[:255]

    try:
        with get_session() as db_session:
            ticket = SupportTicket(channel=channel)
            ticket.name = name
            ticket.email = email
            ticket.description = description
            ticket.page_url = page_url or None
            ticket.user_agent = user_agent or None
            db_session.add(ticket)
            db_session.commit()

            return jsonify(
                {
                    "status": "ok",
                    "ticket_id": ticket.id,
                    "message": "Gracias por tu reporte, lo revisaremos en breve.",
                }
            ), HTTPStatus.CREATED
    except Exception as exc:
        current_app.logger.error("Error creating support ticket: %s", exc, exc_info=True)
        return jsonify(
            {"error": "No pudimos registrar tu reporte, intenta más tarde."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
