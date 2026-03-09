"""
Feedback email endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: pronto-api ya tiene endpoints completos de feedback en /api/feedback/
      Este módulo hace BFF proxy a esos endpoints.
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

feedback_email_bp = Blueprint("client_feedback_email", __name__)


@feedback_email_bp.post("/feedback/email/<token>/submit")
def submit_feedback_with_token(token):
    """PROXY: Submit feedback with email token."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/feedback/email/{token}/submit"
    return forward_to_api("POST", path, data=payload)


@feedback_email_bp.post("/orders/<uuid:order_id>/feedback/email-trigger")
def trigger_feedback_email(order_id: UUID):
    """PROXY: Trigger feedback email after timer expires."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/feedback/orders/{order_id}/feedback/email-trigger"
    return forward_to_api("POST", path, data=payload)


@feedback_email_bp.post("/feedback/bulk")
def submit_bulk_feedback():
    """PROXY: Submit bulk feedback."""
    payload = request.get_json(silent=True) or {}
    return forward_to_api("POST", "/api/feedback/bulk", data=payload)


@feedback_email_bp.post("/feedback/questions")
def get_feedback_questions():
    """PROXY: Get feedback questions."""
    return forward_to_api("POST", "/api/feedback/questions")
