"""
Customer Authentication API - BFF PROXY TO PRONTO-API.
This module is a BFF proxy for customer authentication.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, Response, request, session
from flask_wtf.csrf import generate_csrf

from pronto_shared.serializers import success_response

from ._upstream import forward_to_api

auth_bp = Blueprint("client_auth", __name__, url_prefix="/client-auth")


def _extract_customer_ref(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = str(payload.get("customer_ref") or "").strip()
    if direct:
        return direct
    nested = payload.get("data")
    if isinstance(nested, dict):
        return str(nested.get("customer_ref") or "").strip()
    return ""


def _sync_flask_customer_session_from_response(response_obj: object) -> None:
    payload: object = None
    if isinstance(response_obj, Response):
        payload = response_obj.get_json(silent=True)
    elif isinstance(response_obj, dict):
        payload = response_obj

    customer_ref = _extract_customer_ref(payload)
    if customer_ref:
        session["customer_ref"] = customer_ref
        session.permanent = False


@auth_bp.post("/login")
def login():
    """PROXY: Customer login - forwards to pronto-api /api/client-auth/login"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/login"
    response = forward_to_api("POST", path, data=payload, stream=True)
    if isinstance(response, tuple):
        body, status = response
        if int(status) == HTTPStatus.OK:
            _sync_flask_customer_session_from_response(body)
        return response
    if isinstance(response, Response) and response.status_code == HTTPStatus.OK:
        _sync_flask_customer_session_from_response(response)
    return response


@auth_bp.post("/register")
def register():
    """PROXY: Customer registration - forwards to pronto-api /api/client-auth/register"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/register"
    response = forward_to_api("POST", path, data=payload, stream=True)
    if isinstance(response, tuple):
        body, status = response
        if int(status) in {HTTPStatus.OK, HTTPStatus.CREATED}:
            _sync_flask_customer_session_from_response(body)
        return response
    if isinstance(response, Response) and response.status_code in {
        HTTPStatus.OK,
        HTTPStatus.CREATED,
    }:
        _sync_flask_customer_session_from_response(response)
    return response


@auth_bp.post("/logout")
def logout():
    """PROXY: Customer logout - forwards to pronto-api /api/client-auth/logout"""
    path = "/api/client-auth/logout"
    response = forward_to_api("POST", path, stream=True)
    session.pop("customer_ref", None)
    session.pop("dining_session_id", None)
    return response


@auth_bp.get("/me")
def me():
    """PROXY: Current customer profile - forwards to pronto-api /api/client-auth/me"""
    path = "/api/client-auth/me"
    return forward_to_api("GET", path, stream=True)


@auth_bp.put("/me")
def update_me():
    """PROXY: Update current customer profile - forwards to pronto-api /api/client-auth/me"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/me"
    return forward_to_api("PUT", path, data=payload, stream=True)


@auth_bp.get("/csrf")
def csrf_token():
    """Expose a fresh CSRF token for client-side mutation retries."""
    return success_response({"csrf_token": generate_csrf()}), HTTPStatus.OK
