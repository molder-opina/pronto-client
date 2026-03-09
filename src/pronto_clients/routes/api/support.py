"""
Support endpoints for clients API - BFF PROXY TO PRONTO-API.
This module is a BFF proxy for customer support requests.
All business logic lives in pronto-api:6082 under "/api/*".
This proxy forwards requests without modifying business data.
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations

from flask import Blueprint, request

from ._upstream import forward_to_api

support_bp = Blueprint("client_support", __name__)


@support_bp.post("")
def create_support_ticket():
    """PROXY: Create support ticket - forwards to pronto-api /api/support"""
    payload = request.get_json(silent=True) or {}
    return forward_to_api("POST", "/api/support", data=payload)
