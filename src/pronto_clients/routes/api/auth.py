"""
Customer Authentication API - Redis-backed customer_ref sessions.

Endpoints:
- POST /auth/login - Authenticate customer, create session
- POST /auth/register - Create new customer account
- POST /auth/logout - Revoke customer_ref, clear session
- GET /auth/me - Get current customer info
"""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, session
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


@auth_bp.post("/auth/login")
@auth_bp.post("/login")
@rate_limit(max_requests=5, window_seconds=60, key_prefix="login")
def login():
    """Authenticate customer and create Redis-backed customer_ref session."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email y password requeridos"}), HTTPStatus.BAD_REQUEST

    customer = authenticate_customer(db, email=email, password=password)
    
    # Authenticated successfully. Now fetch full details for session (including tax info)
    if customer:
        from pronto_shared.services.customer_service import get_customer_by_id
        # authenticate_customer returns a dict with 'id', verify it's there
        # but create_customer returns 'id' as str, get_customer_by_id takes int/str?
        # get_customer_by_id takes int but casts to str in SQL.
        full_customer = get_customer_by_id(db, customer["id"])
        if full_customer:
            customer.update(full_customer)

    if not customer:
        return jsonify({"error": "Credenciales inválidas"}), HTTPStatus.UNAUTHORIZED

    try:
        # Create payload with extra fields (tax info)
        payload_extras = {
            "tax_id": customer.get("tax_id"),
            "tax_name": customer.get("tax_name"),
            "tax_address": customer.get("tax_address"),
            "tax_email": customer.get("tax_email")
        }
        
        customer_ref = customer_session_store.create_customer_ref(
            customer_id=str(customer["id"]),
            email=customer.get("email") or "",
            name=customer.get("first_name") or "",
            phone=customer.get("phone"),
            kind=customer.get("kind", "customer"),
            # We can't pass extras to create_customer_ref directly as arguments if the signature doesn't match
            # But we can update the session immediately after?
            # Or reliance on customer_session_store to accept kwargs is risky if not defined.
            # create_customer_ref signature: (self, customer_id, email, name, phone=None, kind='customer', kiosk_location=None)
            # It blindly constructs payload from arguments. It does NOT accept **kwargs.
            # So I must update the session after creation OR modify create_customer_ref.
            # Updating after creation is safer for now.
        )
        
        # Inject extras into the session we just created
        # We need to construct the full payload and update
        full_payload = {
            "customer_id": str(customer["id"]),
            "email": customer.get("email") or "",
            "name": customer.get("first_name") or "",
            "phone": customer.get("phone"),
            "kind": customer.get("kind", "customer"),
            "kiosk_location": customer.get("kiosk_location"),
            **payload_extras
        }
        customer_session_store.update_session(customer_ref, full_payload)
        
    except RedisUnavailableError:
        return jsonify({"error": "Servicio no disponible"}), HTTPStatus.SERVICE_UNAVAILABLE

    session.clear()
    session["customer_ref"] = customer_ref
    session.permanent = True

    return jsonify(
        {
            "success": True,
            "customer": {
                "id": str(customer["id"]),
                "email": customer.get("email"),
                "name": customer.get("first_name") or "",
                "tax_id": customer.get("tax_id"),
                "tax_name": customer.get("tax_name"),
            },
        }
    ), HTTPStatus.OK


@auth_bp.post("/auth/register")
@auth_bp.post("/register")
@rate_limit(max_requests=5, window_seconds=60, key_prefix="register")
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


@auth_bp.post("/auth/logout")
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


@auth_bp.get("/auth/me")
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


@auth_bp.put("/auth/me")
@auth_bp.put("/me")
@customer_session_required
def update_profile():
    """Update current customer info (including tax info)."""
    customer_ref = session.get("customer_ref")
    try:
        current_data = customer_session_store.get_customer(customer_ref)
        if not current_data:
            return jsonify({"error": "Sesión inválida"}), HTTPStatus.UNAUTHORIZED
            
        customer_id = current_data["id"] if "id" in current_data else current_data.get("customer_id")
        data = request.get_json(silent=True) or {}
        
        # Extract fields to update
        update_data = {}
        allowed_fields = [
            "name", "phone", "email", 
            "tax_id", "tax_name", "tax_address", "tax_email"
        ]
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
                
        if "name" in update_data:
            # Split name into first and last
            parts = update_data["name"].split(None, 1)
            update_data["first_name"] = parts[0]
            update_data["last_name"] = parts[1] if len(parts) > 1 else ""
            del update_data["name"]

        updated_customer = None
        with get_session() as db:
            from pronto_shared.services.customer_service import update_customer
            updated_customer = update_customer(db, customer_id, **update_data)
            
        # Update Redis session with merged data
        # Use existing session data as base, overlay updated fields
        new_payload = current_data.copy()
        
        # Map updated_customer keys to session keys
        # updated_customer has keys: id, name, email, phone, tax_...
        # session keys: customer_id, email, name, phone, tax_...
        
        new_payload["name"] = updated_customer.get("name", current_data.get("name"))
        new_payload["email"] = updated_customer.get("email", current_data.get("email"))
        new_payload["phone"] = updated_customer.get("phone", current_data.get("phone"))
        new_payload["tax_id"] = updated_customer.get("tax_id")
        new_payload["tax_name"] = updated_customer.get("tax_name")
        new_payload["tax_address"] = updated_customer.get("tax_address")
        new_payload["tax_email"] = updated_customer.get("tax_email")
        
        customer_session_store.update_session(customer_ref, new_payload)
        
        return jsonify({"success": True, "customer": updated_customer})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
