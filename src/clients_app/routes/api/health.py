"""
Health check endpoint for clients API.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify

health_bp = Blueprint("client_health", __name__)


@health_bp.get("/health")
def healthcheck():
    """Basic endpoint to confirm the container is healthy."""
    return jsonify({"status": "ok"}), HTTPStatus.OK
