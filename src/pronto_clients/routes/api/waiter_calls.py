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

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, request

from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

waiter_calls_bp = Blueprint("client_waiter_calls", __name__)


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
            response = http_requests.get(url, headers=headers, cookies=request.cookies, timeout=5)
        elif method == "POST":
            response = http_requests.post(url, json=data, headers=headers, cookies=request.cookies, timeout=5)
        else:
            from pronto_shared.serializers import error_response
            return error_response("Method not supported"), HTTPStatus.METHOD_NOT_ALLOWED
        
        # Return response from pronto-api
        from pronto_shared.serializers import success_response
        return success_response(response.json()), response.status_code
    
    except http_requests.Timeout:
        from pronto_shared.serializers import error_response
        return error_response("Timeout conectando a API"), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        from pronto_shared.serializers import error_response
        return error_response("Error conectando a API"), HTTPStatus.BAD_GATEWAY


@waiter_calls_bp.post("/call-waiter")
def call_waiter():
    """PROXY: Customer requests a waiter for their table."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/call-waiter"
    return _forward_to_api("POST", path, data=payload)


@waiter_calls_bp.get("/status/<int:call>")
def get_waiter_call_status(call: int):
    """PROXY: Get the status of a waiter call."""
    path = f"/api/customers/waiter-calls/status/{call}"
    return _forward_to_api("GET", path)


@waiter_calls_bp.post("/cancel")
def cancel_waiter_call():
    """PROXY: Cancel a pending waiter call."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/cancel"
    return _forward_to_api("POST", path, data=payload)
