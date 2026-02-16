from flask import Blueprint, jsonify, request, session
from pronto_clients.routes.api.orders import _forward_to_api

sessions_bp = Blueprint("client_sessions_api", __name__)

@sessions_bp.post("/sessions/open")
def open_session():
    payload = request.get_json(silent=True) or {}
    data, status = _forward_to_api("POST", "/api/sessions/open", payload)
    if status == 200:
        # Check if response has session info
        sess_data = data.get("session") or data.get("data", {}).get("session")
        if sess_data:
            session["dining_session_id"] = sess_data.get("id")
    return jsonify(data), status

@sessions_bp.get("/sessions/me")
def get_me():
    data, status = _forward_to_api("GET", "/api/sessions/me")
    return jsonify(data), status
