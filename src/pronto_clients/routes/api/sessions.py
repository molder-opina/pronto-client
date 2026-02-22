from http import HTTPStatus

from flask import Blueprint, jsonify, request, session
from pronto_clients.routes.api.auth import customer_session_required
from pronto_clients.routes.api.orders import _forward_to_api
from pronto_clients.routes.api.table_context import (
    TableContextError,
    persist_table_context,
    resolve_table_context,
)
from pronto_shared.serializers import error_response, success_response

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
            # Forward upstream cookies (access_token is critical)
            # We enforce HttpOnly/Secure defaults if compatible, or try to copy attributes
            # Requests Cookie object: name, value, path, domain, secure, expires
            resp.set_cookie(
                key=cookie.name,
                value=cookie.value,
                path=cookie.path if cookie.path else "/",
                secure=cookie.secure,
                httponly=True if cookie.name == "access_token" else False,
                # domain=cookie.domain # Skip domain proxying to allow localhost
            )
            
    return resp

@sessions_bp.get("/sessions/me")
def get_me():
    data, status, _ = _forward_to_api("GET", "/api/sessions/me")
    return jsonify(data), status


@sessions_bp.get("/sessions/table-context")
@customer_session_required
def get_table_context():
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    try:
        context, _ = resolve_table_context(
            customer_ref, payload={}, enforce_required=False
        )
        return jsonify(success_response({"table_context": context})), HTTPStatus.OK
    except TableContextError as context_error:
        return (
            jsonify(
                error_response(
                    context_error.message,
                    {"code": context_error.code},
                )
            ),
            int(context_error.status),
        )


@sessions_bp.post("/sessions/table-context")
@customer_session_required
def set_table_context():
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    payload = request.get_json(silent=True) or {}

    try:
        context, customer_payload = resolve_table_context(
            customer_ref, payload=payload, enforce_required=True
        )
        persist_table_context(customer_ref, customer_payload, context)
        return jsonify(success_response({"table_context": context})), HTTPStatus.OK
    except TableContextError as context_error:
        return (
            jsonify(
                error_response(
                    context_error.message,
                    {"code": context_error.code},
                )
            ),
            int(context_error.status),
        )
