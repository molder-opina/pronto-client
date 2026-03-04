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

orders_bp = Blueprint("client_orders_api", __name__)


def _resolve_api_base() -> str:
    bases = _resolve_api_bases()
    return bases[0] if bases else "http://api:5000"


def _resolve_api_bases() -> list[str]:
    """
    Build candidate API bases ordered by reliability for container runtime.

    If a configured base points to localhost, prefer internal Docker DNS first.
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
) -> tuple[dict, int, list]:
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
    dining_session_id = session.get("dining_session_id")
    if dining_session_id:
        headers["X-Pronto-Dining-Session-ID"] = str(dining_session_id)

    # NO cookies propagation - clients use session + Redis, not JWT cookies
    # The X-PRONTO-CUSTOMER-REF header is sufficient for backend authentication

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
        return error_response("Error de comunicación con API"), HTTPStatus.BAD_GATEWAY, []

    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    return data, response.status_code, list(response.cookies)


def _extract_session_id(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("session_id"),
        (payload.get("data") or {}).get("session_id")
        if isinstance(payload.get("data"), dict)
        else None,
        (payload.get("session") or {}).get("id")
        if isinstance(payload.get("session"), dict)
        else None,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return None


def _proxy_create_customer_order():
    payload = request.get_json(silent=True) or {}
    data, status, _ = _forward_to_api("POST", "/api/customer/orders", payload)

    if status in (HTTPStatus.OK, HTTPStatus.CREATED):
        session_id = _extract_session_id(data if isinstance(data, dict) else {})
        if session_id:
            session["dining_session_id"] = session_id

    return jsonify(data), status


@orders_bp.post("/customer/orders")
@customer_session_required
def create_customer_order():
    """Canonical customer order creation endpoint."""
    return _proxy_create_customer_order()


@orders_bp.post("/orders")
@customer_session_required
def create_order_legacy_alias():
    """Legacy alias kept for cached clients still posting to /api/orders."""
    return _proxy_create_customer_order()


@orders_bp.get("/orders/send-confirmation")
@orders_bp.post("/orders/send-confirmation")
def send_order_confirmation():
    """
    Trigger order confirmation email for a dining session.
    Supports GET (query string) and POST (json body) for compatibility.
    """
    payload = request.get_json(silent=True) or {}
    session_id = (
        str(payload.get("session_id") or "").strip()
        or str(request.args.get("session_id") or "").strip()
        or str(session.get("dining_session_id") or "").strip()
    )
    if not session_id:
        return jsonify(error_response("session_id is required")), HTTPStatus.BAD_REQUEST

    data, status, _ = _forward_to_api(
        "POST",
        f"/api/customer/orders/session/{session_id}/send-ticket-email",
        {},
    )
    return jsonify(data), status
