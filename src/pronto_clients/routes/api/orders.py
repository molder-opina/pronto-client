"""
Client BFF - Orders Blueprint.
Proxies calls to pronto-api with customer_ref from Flask session.
"""

import json
import requests
from http import HTTPStatus
from uuid import UUID
from flask import Blueprint, jsonify, request, session

from pronto_clients.routes.api.auth import customer_session_required
from pronto_shared.serializers import error_response, success_response
from pronto_shared.trazabilidad import get_logger

orders_bp = Blueprint("client_orders_api", __name__)

logger = get_logger(__name__)


def _get_customer_ref() -> str | None:
    """Get customer_ref from Flask session."""
    return session.get("customer_ref")


def _clear_customer_session():
    """Clear customer session data."""
    session.pop("customer_ref", None)


def _forward_to_api(method: str, endpoint: str, payload: dict | None = None) -> tuple:
    """
    Forward request to pronto-api with customer_ref header and HMAC signature.

    Returns:
        tuple: (response_json, status_code, cookies)
    """
    import os

    api_base_url = os.getenv("PRONTO_API_INTERNAL_URL", "http://api:5000")
    customer_ref = _get_customer_ref()
    
    headers = {"Content-Type": "application/json"}
    if customer_ref:
        headers["X-PRONTO-CUSTOMER-REF"] = customer_ref
        
    # Inject Internal Auth Secret for CSRF Bypass
    internal_secret = os.getenv("PRONTO_INTERNAL_SECRET")
    if internal_secret:
        headers["X-Pronto-Internal-Auth"] = internal_secret

    try:
        body_str = json.dumps(payload) if payload else ""

        from pronto_shared.internal_auth import (
            create_internal_auth_headers,
            is_internal_auth_enabled,
        )

        if is_internal_auth_enabled():
            auth_headers = create_internal_auth_headers(method, endpoint, body_str)
            headers.update(auth_headers)

        url = f"{api_base_url}{endpoint}"

        cookies_dict = dict(request.cookies)
        if method == "GET":
            resp = requests.get(url, headers=headers, cookies=cookies_dict, timeout=10)
        elif method == "POST":
            resp = requests.post(url, data=body_str, headers=headers, cookies=cookies_dict, timeout=10)
        elif method == "PUT":
            resp = requests.put(url, data=body_str, headers=headers, cookies=cookies_dict, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, cookies=cookies_dict, timeout=10)
        else:
            return {"error": "Invalid method"}, HTTPStatus.INTERNAL_SERVER_ERROR, {}

        if resp.status_code == HTTPStatus.UNAUTHORIZED:
            _clear_customer_session()

        try:
            return resp.json(), resp.status_code, resp.cookies
        except Exception:
            return {"error": "Invalid response from API"}, resp.status_code, resp.cookies

    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with pronto-api: {e}")
        return {
            "error": "Error de comunicacion con el servicio central"
        }, HTTPStatus.SERVICE_UNAVAILABLE, {}


@orders_bp.post("/orders")
def create_order():
    """
    Proxy to pronto-api for creating an order.
    Uses customer_ref from session for authentication.
    """
    payload = request.get_json(silent=True) or {}
    data, status, _ = _forward_to_api("POST", "/api/customer/orders", payload)
    return jsonify(data), status


@orders_bp.get("/orders/current")
def get_current_session_orders():
    """
    Get all orders for a session.
    Query params:
        - session_id: Dining session ID (required)
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify(
            error_response("session_id query parameter is required")
        ), HTTPStatus.BAD_REQUEST

    data, status, _ = _forward_to_api("GET", f"/api/orders?session_id={session_id}")
    return jsonify(data), status


@orders_bp.get("/orders/<uuid:order_id>")
def get_order(order_id: UUID):
    """Get a specific order by ID."""
    data, status, _ = _forward_to_api("GET", f"/api/orders/{order_id}")
    return jsonify(data), status


@orders_bp.post("/orders/send-confirmation")
def send_order_confirmation():
    """
    Compatibility endpoint for checkout confirmation email requests.
    Proxies to customer ticket email endpoint using session_id.
    """
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify(error_response("session_id is required")), HTTPStatus.BAD_REQUEST

    data, status, _ = _forward_to_api(
        "POST", f"/api/customer/orders/session/{session_id}/send-ticket-email", {}
    )
    return jsonify(data), status


@orders_bp.post("/feedback/bulk")
@customer_session_required
def submit_feedback_bulk():
    """
    Proxy endpoint for customer feedback submission from client pages.
    Keeps frontend calls same-origin and forwards auth context to pronto-api.
    """
    payload = request.get_json(silent=True) or {}
    data, status, _ = _forward_to_api("POST", "/api/feedback/bulk", payload)
    return jsonify(data), status
