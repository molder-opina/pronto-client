"""
Waiter call endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: This module implements business logic that should live in pronto-api.
# Sunset date: TBD (to be defined in roadmap)
# Reason: pronto-client should not implement business endpoints per AGENTS.md section 12.4.2.
# Single API authority: pronto-api at :6082 under "/api/*".
# Migration plan: Migrate business logic to pronto-api/src/api_app/routes/customers/waiter_calls.py
# Reference: AGENTS.md section 12.4.2, 12.4.3, 12.4.4

NOTE: This is now a BFF proxy to pronto-api. All business logic has been migrated.
"""

from __future__ import annotations

from flask import Blueprint, request

from ._upstream import forward_to_api

waiter_calls_bp = Blueprint("client_waiter_calls", __name__)


@waiter_calls_bp.post("/call-waiter")
def call_waiter():
    """PROXY: Customer requests a waiter for their table."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/call-waiter"
    return forward_to_api("POST", path, data=payload)


@waiter_calls_bp.get("/status/<int:call>")
def get_waiter_call_status(call: int):
    """PROXY: Get the status of a waiter call."""
    path = f"/api/customers/waiter-calls/status/{call}"
    return forward_to_api("GET", path)


@waiter_calls_bp.post("/cancel")
def cancel_waiter_call():
    """PROXY: Cancel a pending waiter call."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customers/waiter-calls/cancel"
    return forward_to_api("POST", path, data=payload)
