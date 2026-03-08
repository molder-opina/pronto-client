"""
Payments endpoints for clients API - BFF PROXY TO PRONTO-API.

This module is a BFF proxy for customer payment requests.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, request

from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

payments_bp = Blueprint("client_payments", __name__)


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
        
        from pronto_shared.serializers import success_response
        return success_response(response.json()), response.status_code
    
    except http_requests.Timeout:
        from pronto_shared.serializers import error_response
        return error_response("Timeout conectando a API"), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        from pronto_shared.serializers import error_response
        return error_response("Error conectando a API"), HTTPStatus.BAD_GATEWAY


@payments_bp.post("/sessions/<uuid:session_id>/pay")
def pay_session(session_id: UUID):
    """PROXY: Pay for session - forwards to pronto-api /api/payments/sessions/{id}/pay"""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay"
    return _forward_to_api("POST", path, data=payload)


@payments_bp.post("/sessions/<uuid:session_id>/pay/cash")
def pay_cash(session_id: UUID):
    """PROXY: Pay with cash - forwards to pronto-api /api/payments/sessions/{id}/pay/cash"""
    payload = request.get_json(silent=True) or {}
    path = f"/api/payments/sessions/{session_id}/pay/cash"
    return _forward_to_api("POST", path, data=payload)


@payments_bp.get("/methods")
def get_payment_methods():
    """PROXY: Get payment methods - forwards to pronto-api /api/payments/methods"""
    path = "/api/payments/methods"
    return _forward_to_api("GET", path)
