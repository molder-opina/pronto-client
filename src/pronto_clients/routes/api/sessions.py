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

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, Response, request

from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

sessions_bp = Blueprint("client_sessions", __name__)


def _forward_to_api(method: str, path: str, data: dict | None = None):
    """
    Forward request to pronto-api.
    
    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    No business logic is applied here.
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    
    headers = {
        "X-PRONTO-CUSTOMER-REF": request.headers.get("X-PRONTO-CUSTOMER-REF", ""),
        "Content-Type": "application/json",
    }
    
    # Forward correlation ID if present
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    csrf_token = request.headers.get("X-CSRFToken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    
    try:
        if method == "GET":
            response = http_requests.get(
                url,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        elif method == "POST":
            response = http_requests.post(
                url,
                json=data,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        else:
            from pronto_shared.serializers import error_response
            return error_response("Method not supported"), HTTPStatus.METHOD_NOT_ALLOWED

        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = [
            (k, v)
            for k, v in response.raw.headers.items()
            if k.lower() not in excluded_headers
        ]

        return Response(
            response.content,
            status=response.status_code,
            headers=response_headers,
            content_type=response.headers.get("Content-Type"),
        )
    
    except http_requests.Timeout:
        from pronto_shared.serializers import error_response
        return error_response("Timeout conectando a API"), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        from pronto_shared.serializers import error_response
        return error_response("Error conectando a API"), HTTPStatus.BAD_GATEWAY


@sessions_bp.get("/sessions/me")
def get_session_me():
    """PROXY: Get current session info."""
    path = "/api/sessions/me"
    return _forward_to_api("GET", path)


@sessions_bp.post("/sessions/open")
def open_session():
    """PROXY: Open new session."""
    payload = request.get_json(silent=True) or {}
    path = "/api/sessions/open"
    return _forward_to_api("POST", path, data=payload)


@sessions_bp.get("/sessions/<uuid:session_id>/timeout")
def session_timeout(session_id: UUID):
    """PROXY: Validate session timeout."""
    path = f"/api/sessions/{session_id}/timeout"
    return _forward_to_api("GET", path)


@sessions_bp.post("/sessions/table-context")
def set_table_context():
    """PROXY: Set table context."""
    payload = request.get_json(silent=True) or {}
    path = "/api/sessions/table-context"
    return _forward_to_api("POST", path, data=payload)


@sessions_bp.get("/sessions/table-context")
def get_table_context():
    """PROXY: Get table context."""
    path = "/api/sessions/table-context"
    return _forward_to_api("GET", path)
