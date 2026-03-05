"""
Customer Payments API - BFF Proxy to pronto-api.

Proxies payment requests to pronto-api at :6082/api/customer/payments/*.
See AGENTS.md section 12: API canónica.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from urllib.parse import urljoin, urlparse

import requests
from flask import Blueprint, current_app, jsonify, request, session
from pronto_clients.routes.api.auth import customer_session_required

from pronto_shared.serializers import error_response
from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

payments_bp = Blueprint("client_payments", __name__)


def _resolve_api_bases() -> list[str]:
    """
    Build candidate API bases ordered by reliability for container runtime.
    Default matches docker-compose service name "api" and internal port 5000.
    """
    configured = [
        (current_app.config.get("API_BASE_URL") or "").strip().rstrip("/"),
        (os.getenv("PRONTO_API_BASE_URL") or "").strip().rstrip("/"),
        (os.getenv("PRONTO_API_INTERNAL_BASE_URL") or "").strip().rstrip("/"),
    ]
    raw_candidates = [value for value in configured if value]
    raw_candidates.append("http://api:5000")

    candidates: list[str] = []
    seen: set[str] = set()

    def append_candidate(url: str) -> None:
        normalized = (url or "").strip().rstrip("/")
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    for raw in raw_candidates:
        parsed = urlparse(raw)
        hostname = (parsed.hostname or "").lower()
        if hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
            append_candidate("http://api:5000")
        append_candidate(raw)

    return candidates


def _forward_to_api(
    method: str,
    path: str,
    payload: dict | None = None,
    params: dict | None = None,
) -> tuple[dict, int]:
    """
    Forward request to pronto-api with customer authentication.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., "/api/customer/payments/sessions/xxx/request-payment")
        payload: JSON body for POST/PUT requests
        params: Query parameters

    Returns:
        Tuple of (response_data, status_code)
    """
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    internal_secret = (os.getenv("PRONTO_INTERNAL_SECRET") or "").strip()
    if internal_secret:
        headers["X-Pronto-Internal-Auth"] = internal_secret

    customer_ref = session.get("customer_ref")
    if customer_ref:
        headers["X-PRONTO-CUSTOMER-REF"] = str(customer_ref)

    response = None
    errors: list[str] = []
    for base_url in _resolve_api_bases():
        target_url = urljoin(f"{base_url}/", path.lstrip("/"))
        try:
            response = requests.request(
                method=method.upper(),
                url=target_url,
                json=payload if payload is not None else None,
                params=params if params else None,
                headers=headers,
                timeout=20,
            )
            break
        except requests.RequestException as exc:
            errors.append(f"{base_url}: {exc}")
            continue

    if response is None:
        logger.error(
            "Error proxying request to API",
            action="forward_to_api",
            path=path,
            error={"message": " | ".join(errors)},
        )
        return error_response("Error de comunicación con API"), HTTPStatus.BAD_GATEWAY

    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    return data, response.status_code


# =============================================================================
# Payment Endpoints - Proxy to pronto-api
# =============================================================================


@payments_bp.post("/sessions/<uuid:session_id>/request-payment")
@customer_session_required
def request_payment(session_id):
    """
    Customer requests payment for their session.
    Proxies to: POST /api/customer/payments/sessions/<id>/request-payment
    """
    payload = request.get_json(silent=True) or {}
    data, status = _forward_to_api(
        "POST",
        f"/api/customer/payments/sessions/{session_id}/request-payment",
        payload=payload,
    )
    return jsonify(data), status


@payments_bp.post("/confirm-tip")
@customer_session_required
def confirm_tip():
    """
    Save tip amount for a session.
    Proxies to: POST /api/customer/payments/sessions/<id>/confirm-tip
    """
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID is required"}), HTTPStatus.BAD_REQUEST

    data, status = _forward_to_api(
        "POST",
        f"/api/customer/payments/sessions/{session_id}/confirm-tip",
        payload=payload,
    )
    return jsonify(data), status


@payments_bp.post("/sessions/<uuid:session_id>/checkout")
@customer_session_required
def request_session_checkout(session_id):
    """
    Request checkout for a dining session.
    Proxies to: GET /api/customer/payments/sessions/<id>/checkout
    """
    data, status = _forward_to_api(
        "GET",
        f"/api/customer/payments/sessions/{session_id}/checkout",
    )
    return jsonify(data), status


@payments_bp.post("/session/<uuid:session_id>/request-check")
@customer_session_required
def request_check(session_id):
    """
    Request check/bill for a dining session.
    Proxies to: POST /api/customer/orders/session/<id>/request-check
    """
    data, status = _forward_to_api(
        "POST",
        f"/api/customer/orders/session/{session_id}/request-check",
    )
    return jsonify(data), status


@payments_bp.get("/session/<uuid:session_id>/validate")
@customer_session_required
def validate_session(session_id):
    """
    Validate if a session exists.
    Proxies to: GET /api/customer/payments/sessions/<id>/validate
    """
    data, status = _forward_to_api(
        "GET",
        f"/api/customer/payments/sessions/{session_id}/validate",
    )
    return jsonify(data), status


@payments_bp.get("/session/<uuid:session_id>/timeout")
@customer_session_required
def get_session_timeout(session_id):
    """
    Return session timeout metadata.
    Proxies to: GET /api/customer/payments/sessions/<id>/timeout
    """
    data, status = _forward_to_api(
        "GET",
        f"/api/customer/payments/sessions/{session_id}/timeout",
    )
    return jsonify(data), status


@payments_bp.get("/session/<uuid:session_id>/orders")
@customer_session_required
def get_session_orders(session_id):
    """
    Get all orders for a specific session.
    Proxies to: GET /api/customer/payments/sessions/<id>/orders
    """
    data, status = _forward_to_api(
        "GET",
        f"/api/customer/payments/sessions/{session_id}/orders",
    )
    return jsonify(data), status


@payments_bp.post("/sessions/<uuid:session_id>/pay")
@customer_session_required
def pay_session(session_id):
    """
    Process payment for a session.
    Proxies to: POST /api/customer/payments/sessions/<id>/pay
    """
    payload = request.get_json(silent=True) or {}
    data, status = _forward_to_api(
        "POST",
        f"/api/customer/payments/sessions/{session_id}/pay",
        payload=payload,
    )
    return jsonify(data), status


@payments_bp.post("/sessions/<uuid:session_id>/stripe/intent")
@customer_session_required
def create_stripe_intent(session_id):
    """Create Stripe PaymentIntent via canonical pronto-api endpoint."""
    data, status = _forward_to_api(
        "POST",
        f"/api/customer/payments/sessions/{session_id}/stripe/intent",
    )
    return jsonify(data), status
