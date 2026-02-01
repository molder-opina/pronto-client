"""
REST API consumed by the employee web dashboard.
Debug and utility endpoints only.
"""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from shared.db import get_session as get_db_session
from shared.logging_config import get_logger
from shared.models import Employee
from shared.security import hash_credentials, hash_identifier
from shared.serializers import error_response, success_response
from shared.config import read_bool
from shared.validation import validate_password

api_bp = Blueprint("employee_api", __name__)
logger = get_logger(__name__)


@api_bp.get("/health")
def healthcheck():
    from flask import current_app
    from sqlalchemy import text

    from shared.db import _engine

    db_status = "ok"
    try:
        if _engine:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
        else:
            db_status = "not_initialized"
    except Exception as e:
        logger.error(f"Health check database error: {e}")
        db_status = "error"

    overall_status = "ok" if db_status == "ok" else "degraded"

    return jsonify(
        {
            "status": overall_status,
            "database": db_status,
            "debug_mode": current_app.config.get("DEBUG_MODE", False),
        }
    )


@api_bp.get("/debug/autofill")
def get_autofill_data():
    """Return autofill data for forms when DEBUG_MODE is enabled."""
    from flask import current_app

    if not read_bool("DEBUG_MODE", "false"):
        return jsonify(error_response("Debug mode not enabled")), 403

    return jsonify(
        success_response(
            {
                "message": "Datos de autocompletado para DEBUG. Password para todos: ChangeMe!123",
                "default_password": "ChangeMe!123",  # nosec B105
                "users": {
                    "system": {
                        "email": "admin@cafeteria.test",
                        "name": "Admin General",
                        "role": "system",
                    },
                    "admin_roles": {
                        "email": "admin.roles@cafeteria.test",
                        "name": "Admin Roles",
                        "role": "admin_roles",
                    },
                    "waiter1": {
                        "email": "juan.mesero@cafeteria.test",
                        "name": "Juan Mesero",
                        "role": "waiter",
                    },
                    "waiter2": {
                        "email": "maria.mesera@cafeteria.test",
                        "name": "Maria Mesera",
                        "role": "waiter",
                    },
                    "waiter3": {
                        "email": "pedro.mesero@cafeteria.test",
                        "name": "Pedro Mesero",
                        "role": "waiter",
                    },
                    "chef1": {
                        "email": "carlos.chef@cafeteria.test",
                        "name": "Carlos Chef",
                        "role": "chef",
                    },
                    "chef2": {
                        "email": "ana.chef@cafeteria.test",
                        "name": "Ana Chef",
                        "role": "chef",
                    },
                    "cashier1": {
                        "email": "laura.cajera@cafeteria.test",
                        "name": "Laura Cajera",
                        "role": "cashier",
                    },
                    "cashier2": {
                        "email": "roberto.cajero@cafeteria.test",
                        "name": "Roberto Cajero",
                        "role": "cashier",
                    },
                    "content": {
                        "email": "sofia.contenido@cafeteria.test",
                        "name": "Sofia Contenido",
                        "role": "content_manager",
                    },
                },
                "test_data": {
                    "customer": {
                        "name": "Cliente Test",
                        "email": "test@example.com",
                        "phone": "+34666123456",
                    },
                    "new_employee": {
                        "name": "Empleado Nuevo",
                        "email": "nuevo@cafeteria.test",
                        "role": "waiter",
                    },
                    "order": {
                        "items": [
                            {"menu_item_id": 1, "quantity": 2},
                            {"menu_item_id": 2, "quantity": 1},
                        ],
                        "notes": "Sin cebolla, por favor",
                    },
                    "payment": {
                        "payment_method": "cash",
                        "tip_percentages": [5, 10, 15, 20],
                        "tip_amount": 5.00,
                    },
                },
            }
        )
    )


@api_bp.post("/debug/orders")
def debug_create_order():
    """Create a synthetic order for debugging workflows (only in debug mode)."""
    if not read_bool("DEBUG_MODE", "false"):
        return jsonify(error_response("Debug mode not enabled")), HTTPStatus.FORBIDDEN

    payload = request.get_json(silent=True) or {}
    customer_payload = payload.get("customer") or {}

    default_email = (
        f"debug+{int((customer_payload.get('name') or 'anon').__hash__()) & 0xFFFF:04d}@local.test"
    )
    customer_data = {
        "name": customer_payload.get("name") or "CLIENTE DEBUG",
        "email": customer_payload.get("email") or default_email,
        "phone": customer_payload.get("phone") or "+525512345678",
    }

    items = payload.get("items") or [{"menu_item_id": 1, "quantity": 1}]

    try:
        from clients_app.services.order_service import create_order as create_client_order
    except ImportError as exc:
        logger.error("Debug order creation unavailable: %s", exc)
        return jsonify(
            error_response("Servicio de órdenes no disponible en modo debug")
        ), HTTPStatus.SERVICE_UNAVAILABLE

    try:
        result, status = create_client_order(
            customer_data=customer_data,
            items_data=items,
            notes=payload.get("notes", "Orden generada en modo DEBUG"),
            tax_rate=current_app.config.get("TAX_RATE", 0.16),
            existing_session_id=payload.get("session_id"),
            table_number=payload.get("table_number")
            or f"Mesa Debug-{int(items.__hash__()) & 0xFFFF}",
            anonymous_client_id="debug",
        )
        return jsonify(result), status
    except Exception as exc:
        logger.error("Error creando orden de debug: %s", exc, exc_info=True)
        return jsonify(
            error_response("No se pudo crear la orden de prueba")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@api_bp.post("/debug/reset-passwords")
def debug_reset_passwords():
    """TEMPORARY: Reset test employee passwords to ChangeMe!123"""
    password = "ChangeMe!123"  # nosec B105
    validate_password(password)

    test_employees = [
        "admin@cafeteria.test",
        "carlos.chef@cafeteria.test",
        "juan.mesero@cafeteria.test",
    ]

    results = []
    with get_db_session() as db:
        for email in test_employees:
            email_hash = hash_identifier(email)
            employee = db.query(Employee).filter(Employee.email_hash == email_hash).first()

            if employee:
                employee.auth_hash = hash_credentials(employee.email, password)
                results.append(f"✓ Reset: {employee.email}")
            else:
                results.append(f"✗ Not found: {email}")

        db.commit()

    return jsonify({"message": "Passwords reset", "results": results}), 200
