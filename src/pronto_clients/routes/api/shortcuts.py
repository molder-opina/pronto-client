"""Client UI proxy routes."""

import json
from urllib.parse import urljoin
from urllib.request import urlopen

from flask import Blueprint, jsonify
from pronto_clients.routes.api.orders import _forward_to_api

shortcuts_bp = Blueprint("client_shortcuts", __name__)


@shortcuts_bp.get("/shortcuts")
def get_enabled_shortcuts():
    """Proxy endpoint to fetch shortcuts from the main API."""
    data, status, _ = _forward_to_api("GET", "/api/shortcuts")
    return jsonify(data), status


@shortcuts_bp.post("/feedback/questions")
def get_feedback_questions():
    data, status, _ = _forward_to_api("POST", "/api/feedback/questions", {})
    return jsonify(data), status
