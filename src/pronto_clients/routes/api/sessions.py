from flask import Blueprint, jsonify, request, session

from pronto_clients.routes.api.orders import _forward_to_api

sessions_bp = Blueprint("client_sessions_api", __name__)

@sessions_bp.post("/sessions/open")
def open_session():
    payload = request.get_json(silent=True) or {}
    data, status, cookies = _forward_to_api("POST", "/api/sessions/open", payload)
    if status == 200:
        # Check if response has session info
        sess_data = data.get("session") or data.get("data", {}).get("session")
        if sess_data:
            session["dining_session_id"] = sess_data.get("id")
    
    resp = jsonify(data)
    resp.status_code = status
    
    if cookies:
        for cookie in cookies:
            # Forward upstream cookies (client session cookie is security-critical)
            # We enforce HttpOnly/Secure defaults if compatible, or try to copy attributes
            # Requests Cookie object: name, value, path, domain, secure, expires
            resp.set_cookie(
                key=cookie.name,
                value=cookie.value,
                path=cookie.path if cookie.path else "/",
                secure=cookie.secure,
                httponly=True if cookie.name == "pronto_client_session" else False,
                # domain=cookie.domain # Skip domain proxying to allow localhost
            )
            
    return resp

@sessions_bp.get("/sessions/me")
def get_me():
    data, status, _ = _forward_to_api("GET", "/api/sessions/me")
    return jsonify(data), status


@sessions_bp.get("/sessions/table-context")
def get_table_context():
    data, status, _ = _forward_to_api("GET", "/api/sessions/table-context")
    return jsonify(data), status


@sessions_bp.post("/sessions/table-context")
def set_table_context():
    payload = request.get_json(silent=True) or {}
    data, status, _ = _forward_to_api("POST", "/api/sessions/table-context", payload)
    return jsonify(data), status
