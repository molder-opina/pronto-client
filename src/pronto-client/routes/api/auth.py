"""
Authentication endpoints for clients API.
"""

import logging
import secrets
from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from clients_app.utils.input_sanitizer import (
    InputValidationError,
    sanitize_customer_name,
    sanitize_email,
    sanitize_phone,
)

from pronto_shared.jwt_service import create_client_token
from pronto_shared.serializers import success_response, error_response

logger = logging.getLogger(__name__)

auth_bp = Blueprint("client_auth", __name__)


@auth_bp.post("/auth/password/recover")
def recover_password():
    """
    Request password recovery.
    Sends a recovery email with a reset token.

    Body: { "email": "user@example.com" }
    Returns: { "message": "Si el email existe, recibirás un enlace de recuperación" }
    """
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import Customer
    from pronto_shared.security import hash_identifier

    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not email:
        return jsonify({"error": "El email es requerido"}), HTTPStatus.BAD_REQUEST

    try:
        sanitized_email = sanitize_email(email)
    except InputValidationError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            email_hash = hash_identifier(sanitized_email)
            customer = (
                db_session.execute(select(Customer).where(Customer.email_hash == email_hash))
                .scalars()
                .first()
            )

            # Always return success to prevent email enumeration
            if not customer:
                current_app.logger.info(
                    f"Password recovery requested for non-existent email: {sanitized_email}"
                )
                return jsonify(
                    {
                        "status": "ok",
                        "message": "Si el email está registrado, recibirás un enlace de recuperación",
                    }
                ), HTTPStatus.OK

            # Generate reset token
            reset_token = secrets.token_urlsafe(32)
            datetime.utcnow() + timedelta(hours=1)

            # Store reset token (would need a new field in Customer model in production)
            # For now, we log the token for testing
            current_app.logger.info(
                f"[PASSWORD RECOVERY] Token for {customer.email}: {reset_token}"
            )

            # In production, send email here:
            # send_recovery_email(customer.email, reset_token)

            return jsonify(
                {
                    "status": "ok",
                    "message": "Si el email está registrado, recibirás un enlace de recuperación",
                    # Include token in development for testing
                    **({"debug_token": reset_token} if current_app.debug else {}),
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error requesting password recovery: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al procesar la solicitud"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.post("/auth/password/reset")
def reset_password():
    """
    Reset password with recovery token.

    Body: { "token": "reset_token", "password": "new_password" }
    Returns: { "status": "ok", "message": "Contraseña actualizada" }
    """

    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    password = payload.get("password")

    if not token:
        return jsonify({"error": "El token de recuperación es requerido"}), HTTPStatus.BAD_REQUEST

    if not password or len(password) < 6:
        return jsonify(
            {"error": "La contraseña debe tener al menos 6 caracteres"}
        ), HTTPStatus.BAD_REQUEST

    try:
        # In production, validate token against database
        # For now, we accept any non-empty token in development
        if not current_app.debug and not token:
            return jsonify({"error": "Token inválido"}), HTTPStatus.BAD_REQUEST

        # In production, look up customer by token
        # For this demo, we'll just return success if token exists
        return jsonify(
            {"status": "ok", "message": "Contraseña actualizada correctamente"}
        ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error resetting password: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al restablecer la contraseña"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.post("/auth/register")
def register_customer():
    """Register or login a customer with minimal data."""
    from pronto_shared.db import get_session
    from pronto_shared.models import Customer

    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    email = payload.get("email")
    phone = payload.get("phone")

    if not name:
        return jsonify({"error": "El nombre es requerido"}), HTTPStatus.BAD_REQUEST

    if not email:
        return jsonify({"error": "El email es requerido"}), HTTPStatus.BAD_REQUEST

    try:
        sanitized_name = sanitize_customer_name(name)
        sanitized_email = sanitize_email(email)
        sanitized_phone = sanitize_phone(phone)
    except InputValidationError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            customer = None
            if email:
                from sqlalchemy import select

                from pronto_shared.security import hash_identifier

                email_hash = hash_identifier(sanitized_email)
                customer = (
                    db_session.execute(select(Customer).where(Customer.email_hash == email_hash))
                    .scalars()
                    .first()
                )

            if customer:
                return jsonify(
                    {"error": "Este email ya está registrado. Por favor inicia sesión."}
                ), HTTPStatus.CONFLICT

            customer = Customer()
            customer.name = sanitized_name
            customer.email = sanitized_email
            customer.phone = sanitized_phone or ""

            try:
                db_session.add(customer)
                db_session.commit()
                db_session.refresh(customer)
            except IntegrityError:
                # Race condition: another request registered the same email concurrently
                db_session.rollback()
                logger.warning(
                    f"Race condition detected during customer registration for email hash: {email_hash}"
                )
                return jsonify(
                    {"error": "Este email ya está registrado. Por favor inicia sesión."}
                ), HTTPStatus.CONFLICT

            # Create JWT token for the new customer
            access_token = create_client_token(
                customer_id=customer.id,
                customer_name=customer.name,
                customer_phone=customer.phone
            )

            response_data = {
                "status": "ok",
                "access_token": access_token,
                "user": {
                    "id": customer.id,
                    "name": customer.name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "avatar": customer.avatar,
                    "created_at": customer.created_at.isoformat()
                    if customer.created_at
                    else None,
                },
            }

            from flask import make_response
            response = make_response(jsonify(response_data), HTTPStatus.CREATED)

            # Set JWT cookie
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=86400, # 24 hours
                path="/"
            )

            return response

    except Exception as e:
        current_app.logger.error(f"Error registering customer: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al registrar usuario. Por favor intenta de nuevo."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.post("/auth/login")
def login_customer():
    """Login a customer with email."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import Customer

    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not email:
        return jsonify({"error": "El email es requerido"}), HTTPStatus.BAD_REQUEST

    try:
        sanitized_email = sanitize_email(email)
    except InputValidationError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            from pronto_shared.security import hash_identifier

            email_hash = hash_identifier(sanitized_email)
            customer = (
                db_session.execute(select(Customer).where(Customer.email_hash == email_hash))
                .scalars()
                .first()
            )

            if not customer:
                return jsonify(
                    {"error": "No se encontró una cuenta con este email"}
                ), HTTPStatus.NOT_FOUND

            # Create JWT token
            access_token = create_client_token(
                customer_id=customer.id,
                customer_name=customer.name,
                customer_phone=customer.phone
            )

            response_data = {
                "status": "ok",
                "access_token": access_token,
                "user": {
                    "id": customer.id,
                    "name": customer.name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "avatar": customer.avatar,
                    "created_at": customer.created_at.isoformat()
                    if customer.created_at
                    else None,
                },
            }

            from flask import make_response
            response = make_response(jsonify(response_data), HTTPStatus.OK)

            # Set JWT cookie
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=86400, # 24 hours
                path="/"
            )

            return response

    except Exception as e:
        current_app.logger.error(f"Error logging in customer: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al iniciar sesión. Por favor intenta de nuevo."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.put("/auth/update/<int:customer_id>")
def update_customer(customer_id: int):
    """Update customer profile."""
    from pronto_shared.db import get_session
    from pronto_shared.models import Customer

    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    email = payload.get("email")
    phone = payload.get("phone")

    if not name:
        return jsonify({"error": "Name is required"}), HTTPStatus.BAD_REQUEST

    if not email and not phone:
        return jsonify({"error": "Either email or phone is required"}), HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        customer = db_session.get(Customer, customer_id)

        if not customer:
            return jsonify({"error": "Customer not found"}), HTTPStatus.NOT_FOUND

        customer.name = name
        customer.email = email
        customer.phone = phone
        customer.updated_at = datetime.utcnow()

        db_session.commit()
        db_session.refresh(customer)

        return jsonify(
            {
                "status": "ok",
                "user": {
                    "id": customer.id,
                    "name": customer.name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "avatar": customer.avatar,
                    "created_at": customer.created_at.isoformat(),
                },
            }
        ), HTTPStatus.OK


@auth_bp.get("/avatars")
def get_available_avatars():
    """Get list of available predefined avatars."""
    from pathlib import Path

    avatars_dir = Path(current_app.static_folder) / "avatars"

    if not avatars_dir.exists():
        return jsonify({"avatars": []}), HTTPStatus.OK

    avatar_files = sorted([f.name for f in avatars_dir.glob("*.svg")])

    avatars = [
        {
            "filename": filename,
            "url": f"/static/avatars/{filename}",
            "name": filename.replace("avatar-", "").replace(".svg", "").upper(),
        }
        for filename in avatar_files
    ]

    return jsonify({"avatars": avatars}), HTTPStatus.OK


@auth_bp.patch("/auth/update/<int:customer_id>/avatar")
def update_customer_avatar(customer_id: int):
    """Update customer avatar."""
    from pathlib import Path

    from pronto_shared.db import get_session
    from pronto_shared.models import Customer

    payload = request.get_json(silent=True) or {}
    avatar = payload.get("avatar")

    if not avatar:
        return jsonify({"error": "Avatar filename is required"}), HTTPStatus.BAD_REQUEST

    avatars_dir = Path(current_app.static_folder) / "avatars"
    avatar_path = avatars_dir / avatar

    if not avatar_path.exists():
        return jsonify({"error": "Avatar not found"}), HTTPStatus.NOT_FOUND

    with get_session() as db_session:
        customer = db_session.get(Customer, customer_id)

        if not customer:
            return jsonify({"error": "Customer not found"}), HTTPStatus.NOT_FOUND

        customer.avatar = avatar

        db_session.commit()
        db_session.refresh(customer)

        return jsonify(
            {
                "status": "ok",
                "user": {
                    "id": customer.id,
                    "name": customer.name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "avatar": customer.avatar,
                    "created_at": customer.created_at.isoformat(),
                },
            }
        ), HTTPStatus.OK
