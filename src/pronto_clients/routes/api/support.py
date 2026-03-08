"""
Support endpoints for clients API - BFF PROXY TO PRONTO-API.
This module is a BFF proxy for customer support requests.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations
import requests as http_requests
from http import HTTPStatus
from flask import Blueprint, request
from pronto_shared.serializers import success_response
from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url
logger = get_logger(__name__)
support_bp = Blueprint("client_support", __name__)
def _forward_to_api(method: str, path: str, data: dict | None = None):
    """
    Forward request to pronto-api.
    
    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    No business logic is applied here.
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    
    headers = {
        "Content-Type": "application/json",
        "X-PRONTO-CUSTOMER-REF": request.headers.get("X-PRONTO-CUSTOMER-REF", ""),
    }
    
    # Forward correlation ID if present
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    csrf_token = request.headers.get("X-CSRFToken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    
    try:
        if method == "POST":
            response = http_requests.post(url, json=data, headers=headers, cookies=request.cookies, timeout=5)
        else:
            from pronto_shared.serializers import error_response
            return error_response("Method not supported"), HTTPStatus.METHOD_NOT_ALLOWED
        
        return success_response(response.json()), response.status_code
    
    except http_requests.Timeout:
        from pronto_shared.serializers import error_response
        return error_response("Timeout conectando a API"), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        from pronto_shared.serializers import error_response
        return error_response("Error conectando a API"), HTTPStatus.BAD_GATEWAY
@support_bp.post("")
def create_support_ticket():
    """PROXY: Create support ticket - forwards to pronto-api /api/support"""
    payload = request.get_json(silent=True) or {}
    path = "/api/support"
    return _forward_to_api("POST", path, data=payload)
