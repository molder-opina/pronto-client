"""
Support ticket endpoints for clients API.
"""

import os
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from pronto_clients.utils.input_sanitizer import (
    InputValidationError,
    sanitize_customer_name,
    sanitize_email,
    sanitize_support_description,
)
from pronto_shared.db import get_session
from pronto_shared.models import SupportTicket
from pronto_shared.services.email_service import send_template_email
from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

support_bp = Blueprint("client_support", __name__)

DEFAULT_SUPPORT_REPORT_EMAIL = "luartx@gmail.com"


def _resolve_support_recipient() -> str:
    configured = (
        os.getenv("SUPPORT_REPORT_TO")
        or os.getenv("SUPPORT_EMAIL_TO")
        or os.getenv("SUPPORT_EMAIL")
        or DEFAULT_SUPPORT_REPORT_EMAIL
    )
    return configured.strip() or DEFAULT_SUPPORT_REPORT_EMAIL


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

    category = (payload.get("category") or "other").strip().lower()[:64] or "other"
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

            recipient = _resolve_support_recipient()
            restaurant_name = current_app.config.get("RESTAURANT_NAME", "Pronto")
            subject = f"[Soporte Cliente] Ticket #{ticket.id} - {restaurant_name}"
            html = f"""
                <h2>Nuevo reporte de soporte técnico</h2>
                <p><strong>Ticket:</strong> #{ticket.id}</p>
                <p><strong>Categoría:</strong> {category}</p>
                <p><strong>Canal:</strong> {channel}</p>
                <p><strong>Nombre:</strong> {name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Página:</strong> {page_url or "N/A"}</p>
                <p><strong>User-Agent:</strong> {user_agent or "N/A"}</p>
                <hr />
                <p><strong>Descripción:</strong></p>
                <pre style="white-space: pre-wrap; font-family: inherit;">{description}</pre>
            """
            email_sent = send_template_email(
                to_email=recipient,
                subject=subject,
                html_content=html,
                template_name="support_ticket",
            )

            return jsonify(
                {
                    "status": "ok",
                    "ticket_id": ticket.id,
                    "email_sent": bool(email_sent),
                    "message": "Gracias por tu reporte, lo revisaremos en breve.",
                }
            ), HTTPStatus.CREATED
    except Exception as exc:
        logger.error("Error creating support ticket", error={"exception": str(exc), "traceback": True})
        return jsonify(
            {"error": "No pudimos registrar tu reporte, intenta más tarde."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
