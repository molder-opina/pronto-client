"""
Customer Authentication API - Redis-backed customer_ref sessions.

Endpoints:
- POST /login - Authenticate customer, create session
- POST /register - Create new customer account
- POST /logout - Revoke customer_ref, clear session
- GET /me - Get current customer info
"""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, session
from pronto_shared.extensions import csrf
from pronto_shared.db import get_session
from pronto_shared.services.customer_service import (
    authenticate_customer,
    create_customer,
)
from pronto_shared.services.customer_session_store import (
    customer_session_store,
    RedisUnavailableError,
)
from pronto_shared.security_middleware import rate_limit

auth_bp = Blueprint("client_auth", __name__)


from pronto_shared.security_middleware import rate_limit


@auth_bp.post("/register")
@rate_limit(limit="5/minute", key_prefix="register")
def register():
    """
    Create new customer account and auto-login.

    Request JSON:
        - name: Full name
        - email: Customer email
        - password: Customer password (min 6 chars)
        - phone: Phone number (optional)

    Returns:
        - 201: {success: true, customer: {...}}
        - 400: {error: "Email ya registrado"} or validation error
        - 503: {error: "Servicio no disponible"} if Redis down
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), HTTPStatus.BAD_REQUEST

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    phone = data.get("phone", "").strip() or None

    if not name or not email or not password:
        return jsonify(
            {"error": "Nombre, email y password requeridos"}
        ), HTTPStatus.BAD_REQUEST

    if len(password) < 6:
        return jsonify(
            {"error": "Password debe tener al menos 6 caracteres"}
        ), HTTPStatus.BAD_REQUEST

    parts = name.split(None, 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else None

    with get_session() as db:
        try:
            customer = create_customer(
                db,
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                phone=phone,
                kind="customer",
            )
        except ValueError as e:
            if "already registered" in str(e).lower():
                return jsonify({"error": "Email ya registrado"}), HTTPStatus.BAD_REQUEST
            return jsonify({"error": str(e)}), HTTPStatus.BAD_REQUEST

    try:
        customer_ref = customer_session_store.create_customer_ref(
            customer_id=customer["id"],
            email=customer["email"],
            name=customer["first_name"],
            phone=customer.get("phone"),
            kind=customer.get("kind", "customer"),
        )
    except RedisUnavailableError:
        return jsonify(
            {
                "error": "Cuenta creada pero no se pudo iniciar sesion. Intenta login manual."
            }
        ), HTTPStatus.CREATED

    session.clear()
    session["customer_ref"] = customer_ref
    session.permanent = True

    return jsonify(
        {
            "success": True,
            "customer": {
                "id": customer["id"],
                "email": customer["email"],
                "name": customer["first_name"],
            },
        }
    ), HTTPStatus.CREATED


@auth_bp.post("/logout")
def logout():
    """
    Revoke customer_ref and clear session.

    Returns:
        - 200: {success: true}
    """
    from flask import make_response

    customer_ref = session.get("customer_ref")

    if customer_ref:
        try:
            customer_session_store.revoke(customer_ref)
        except RedisUnavailableError:
            pass

    session.clear()
    session.modified = True

    response = make_response(jsonify({"success": True}))
    response.delete_cookie("session")
    return response


from functools import wraps


def customer_session_required(f):
    """Decorator to protect routes requiring a valid customer session."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        customer_ref = session.get("customer_ref")
        if not customer_ref:
            return jsonify({"error": "No autenticado"}), HTTPStatus.UNAUTHORIZED
        try:
            if customer_session_store.is_revoked(customer_ref):
                session.clear()
                session.modified = True
                return jsonify({"error": "Sesión inválida"}), HTTPStatus.UNAUTHORIZED
        except RedisUnavailableError:
            return (
                jsonify({"error": "Servicio no disponible"}),
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        # Do not catch generic Exception here to avoid hiding other issues
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.get("/me")
@customer_session_required
def me():
    """
    Get current customer info from Redis.
    Assumes customer session is valid due to decorator.

    Returns:
        - 200: {customer: {...}} or {customer: null}
    """
    customer_ref = session.get("customer_ref")

    try:
        customer = customer_session_store.get_customer(customer_ref)
    except RedisUnavailableError:
        return (
            jsonify({"error": "Servicio no disponible"}),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except Exception:
        # Avoid clearing session on unknown error, just signal failure
        return (
            jsonify({"error": "Error interno del servidor"}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    if not customer:
        # The ref was valid but data is gone? Clear session.
        session.clear()
        session.modified = True
        return jsonify({"customer": None})

    return jsonify({"customer": customer})
