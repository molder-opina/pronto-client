"""
Customer Authentication API - BFF PROXY TO PRONTO-API.
This module is a BFF proxy for customer authentication.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations
import requests as http_requests
from http import HTTPStatus
from flask import Blueprint, Response, jsonify, request
from flask_wtf.csrf import generate_csrf
from pronto_shared.serializers import success_response
from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url
logger = get_logger(__name__)
auth_bp = Blueprint("client_auth", __name__, url_prefix="/client-auth")
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
        elif method == "PUT":
            response = http_requests.put(
                url,
                json=data,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        else:
            return jsonify({"error": "Method not supported"}), HTTPStatus.METHOD_NOT_ALLOWED

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
        return jsonify({"error": "Timeout conectando a API"}), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        return jsonify({"error": "Error conectando a API"}), HTTPStatus.BAD_GATEWAY
@auth_bp.post("/login")
def login():
    """PROXY: Customer login - forwards to pronto-api /api/client-auth/login"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/login"
    return _forward_to_api("POST", path, data=payload)
@auth_bp.post("/register")
def register():
    """PROXY: Customer registration - forwards to pronto-api /api/client-auth/register"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/register"
    return _forward_to_api("POST", path, data=payload)
@auth_bp.post("/logout")
def logout():
    """PROXY: Customer logout - forwards to pronto-api /api/client-auth/logout"""
    path = "/api/client-auth/logout"
    return _forward_to_api("POST", path)


@auth_bp.get("/me")
def me():
    """PROXY: Current customer profile - forwards to pronto-api /api/client-auth/me"""
    path = "/api/client-auth/me"
    return _forward_to_api("GET", path)


@auth_bp.put("/me")
def update_me():
    """PROXY: Update current customer profile - forwards to pronto-api /api/client-auth/me"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/me"
    return _forward_to_api("PUT", path, data=payload)


@auth_bp.get("/csrf")
def csrf_token():
    """Expose a fresh CSRF token for client-side mutation retries."""
    return success_response({"csrf_token": generate_csrf()}), HTTPStatus.OK
