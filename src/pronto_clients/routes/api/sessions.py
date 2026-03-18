"""
Sessions endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: pronto-api ya tiene endpoints completos de sesiones en /api/client_sessions/
      Este módulo hace BFF proxy a esos endpoints.
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

sessions_bp = Blueprint("client_sessions", __name__)


@sessions_bp.get("/sessions/me")
def get_session_me():
    """PROXY: Get current session info."""
    return forward_to_api("GET", "/api/sessions/me", stream=True)


@sessions_bp.post("/sessions/open")
def open_session():
    """PROXY: Open new session."""
    payload = request.get_json(silent=True) or {}
    return forward_to_api("POST", "/api/sessions/open", data=payload, stream=True)


@sessions_bp.get("/sessions/<uuid:session_id>/timeout")
def session_timeout(session_id: UUID):
    """PROXY: Validate session timeout."""
    path = f"/api/sessions/{session_id}/timeout"
    return forward_to_api("GET", path, stream=True)


@sessions_bp.post("/sessions/table-context")
def set_table_context():
    """PROXY: Set table context."""
    payload = request.get_json(silent=True) or {}
    return forward_to_api("POST", "/api/sessions/table-context", data=payload, stream=True)


@sessions_bp.get("/sessions/table-context")
def get_table_context():
    """PROXY: Get table context."""
    return forward_to_api("GET", "/api/sessions/table-context", stream=True)


@sessions_bp.post("/sessions/validate-and-rehydrate")
def validate_and_rehydrate_session():
    """PROXY: Validate current customer session and rehydrate state."""
    return forward_to_api("POST", "/api/sessions/validate-and-rehydrate", stream=True)
