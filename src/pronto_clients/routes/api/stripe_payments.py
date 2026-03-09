"""
Stripe and Clip payment endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api/src/api_app/routes/payments.py
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: This is now a BFF proxy to pronto-api. All business logic has been migrated.
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

stripe_payments_bp = Blueprint("client_stripe_payments", __name__)


@stripe_payments_bp.post("/sessions/<uuid:session_id>/pay/stripe")
def pay_with_stripe(session_id: UUID):
    """PROXY: Process payment with Stripe for a dining session."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay/stripe"
    return forward_to_api("POST", path, data=payload)


@stripe_payments_bp.post("/sessions/<uuid:session_id>/pay/clip")
def pay_with_clip(session_id: UUID):
    """PROXY: Register a Clip/Terminal payment request for a dining session."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay/clip"
    return forward_to_api("POST", path, data=payload)
