"""
Payments endpoints for clients API - BFF PROXY TO PRONTO-API.

This module is a BFF proxy for customer payment requests.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

payments_bp = Blueprint("client_payments", __name__)


@payments_bp.post("/sessions/<uuid:session_id>/pay")
def pay_session(session_id: UUID):
    """PROXY: Pay for session - forwards to pronto-api /api/payments/sessions/{id}/pay"""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay"
    return forward_to_api("POST", path, data=payload)


@payments_bp.post("/sessions/<uuid:session_id>/pay/cash")
def pay_cash(session_id: UUID):
    """PROXY: Pay with cash - forwards to pronto-api /api/payments/sessions/{id}/pay/cash"""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay/cash"
    return forward_to_api("POST", path, data=payload)


@payments_bp.get("/methods")
def get_payment_methods():
    """PROXY: Get payment methods - forwards to pronto-api /api/payments/methods"""
    path = "/api/payments/methods"
    return forward_to_api("GET", path)
