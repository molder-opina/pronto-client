"""
Client BFF - Orders Blueprint.
Proxies calls to pronto-api with customer_ref from Flask session.
"""

import json
import logging
import requests
from http import HTTPStatus
from flask import Blueprint, current_app, jsonify, request, session

from pronto_shared.serializers import error_response, success_response

orders_bp = Blueprint("client_orders_api", __name__)

logger = logging.getLogger(__name__)


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
        tuple: (response_json, status_code)
    """
    import os

    api_base_url = os.getenv("PRONTO_API_INTERNAL_URL", "http://api:5000")
    customer_ref = _get_customer_ref()

    headers = {"Content-Type": "application/json"}
    if customer_ref:
        headers["X-PRONTO-CUSTOMER-REF"] = customer_ref

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

        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            resp = requests.post(url, data=body_str, headers=headers, timeout=10)
        elif method == "PUT":
            resp = requests.put(url, data=body_str, headers=headers, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=10)
        else:
            return {"error": "Invalid method"}, HTTPStatus.INTERNAL_SERVER_ERROR

        if resp.status_code == HTTPStatus.UNAUTHORIZED:
            _clear_customer_session()

        try:
            return resp.json(), resp.status_code
        except Exception:
            return {"error": "Invalid response from API"}, resp.status_code

    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with pronto-api: {e}")
        return {
            "error": "Error de comunicacion con el servicio central"
        }, HTTPStatus.SERVICE_UNAVAILABLE


@orders_bp.post("/orders")
def create_order():
    """
    Proxy to pronto-api for creating an order.
    Uses customer_ref from session for authentication.
    """
    payload = request.get_json(silent=True) or {}
    data, status = _forward_to_api("POST", "/api/customer/orders", payload)
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

    data, status = _forward_to_api("GET", f"/api/orders?session_id={session_id}")
    return jsonify(data), status


@orders_bp.get("/orders/<int:order_id>")
def get_order(order_id: int):
    """Get a specific order by ID."""
    data, status = _forward_to_api("GET", f"/api/orders/{order_id}")
    return jsonify(data), status
