"""
Customer Authentication API - BFF PROXY TO PRONTO-API.
This module is a BFF proxy for customer authentication.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, request
from flask_wtf.csrf import generate_csrf

from pronto_shared.serializers import success_response

from ._upstream import forward_to_api

auth_bp = Blueprint("client_auth", __name__, url_prefix="/client-auth")


@auth_bp.post("/login")
def login():
    """PROXY: Customer login - forwards to pronto-api /api/client-auth/login"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/login"
    return forward_to_api("POST", path, data=payload, stream=True)


@auth_bp.post("/register")
def register():
    """PROXY: Customer registration - forwards to pronto-api /api/client-auth/register"""
    payload = request.get_json(silent=True) or {}
    path = "/api/client-auth/register"
    return forward_to_api("POST", path, data=payload, stream=True)


@auth_bp.post("/logout")
def logout():
    """PROXY: Customer logout - forwards to pronto-api /api/client-auth/logout"""
    path = "/api/client-auth/logout"
    return forward_to_api("POST", path, stream=True)


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
