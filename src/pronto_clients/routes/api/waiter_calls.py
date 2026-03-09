"""
Waiter call endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api/src/api_app/routes/customers/waiter_calls.py
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: This is now a BFF proxy to pronto-api. All business logic has been migrated.
"""

from __future__ import annotations

from flask import Blueprint, request

from ._upstream import forward_to_api

waiter_calls_bp = Blueprint("client_waiter_calls", __name__)


@waiter_calls_bp.post("/call-waiter")
def call_waiter():
    """PROXY: Customer requests a waiter for their table."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/call-waiter"
    return forward_to_api("POST", path, data=payload)


@waiter_calls_bp.get("/status/<int:call>")
def get_waiter_call_status(call: int):
    """PROXY: Get the status of a waiter call."""
    path = f"/api/customers/waiter-calls/status/{call}"
    return forward_to_api("GET", path)


@waiter_calls_bp.post("/cancel")
def cancel_waiter_call():
    """PROXY: Cancel a pending waiter call."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/cancel"
    return forward_to_api("POST", path, data=payload)
