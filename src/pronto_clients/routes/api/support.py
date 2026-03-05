"""
Support ticket proxy endpoint for clients API.
"""

from http import HTTPStatus
from flask import Blueprint, jsonify, request
from pronto_clients.routes.api.orders import _forward_to_api

support_bp = Blueprint("client_support", __name__)

@support_bp.post("/support-tickets")
def create_support_ticket():
    """Proxy endpoint to create a support ticket via the main API."""
    payload = request.get_json(silent=True) or {}
    data, status, _ = _forward_to_api("POST", "/api/support-tickets", payload)
    return jsonify(data), status
