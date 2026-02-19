"""
Customer facing web views rendered via Jinja templates.
"""

from __future__ import annotations

import os
from uuid import UUID
from flask import Blueprint, current_app, render_template, request, session, jsonify
from sqlalchemy import select
from pronto_shared.trazabilidad import get_logger

from pronto_shared.db import get_session
from pronto_shared.jwt_middleware import get_current_user
from pronto_shared.models import Area, Table, DiningSession
from pronto_shared.services.customer_service import (
    get_customer_by_email,
    authenticate_customer,
)
from pronto_shared.services.customer_session_store import (
    customer_session_store,
    RedisUnavailableError,
)

web_bp = Blueprint("client_web", __name__)

_KIOSK_SECRET = os.getenv("PRONTO_KIOSK_SECRET", "")
_KIOSK_PASSWORD = os.getenv(
    "PRONTO_KIOSK_PASSWORD", "kiosk-no-auth-change-in-production"
)


@web_bp.get("/")
def home():
    """
    Landing page that consumes the API via HTMX/fetch for a richer experience.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    customer_data = get_current_user()

    # Fetch available tables for debug panel
    available_tables = []
    if debug_auto_table or True:  # Always fetch for now to support debug panel
        try:
            from pronto_shared.models import Table, Area

            with get_session() as db_session:
                results = db_session.execute(
                    select(Table, Area)
                    .join(Area, Table.area_id == Area.id)
                    .order_by(Area.prefix, Area.name, Table.table_number)
                ).all()
                available_tables = [
                    {
                        "table_number": t.table_number,
                        "area": {"prefix": a.prefix, "name": a.name},
                        "id": t.id,
                    }
                    for t, a in results
                ]
        except Exception as e:
            logger = get_logger("clients.web")
            logger.error(
                f"Error fetching tables for debug: {e}", error={"message": str(e)}
            )

    return render_template(
        "index.html",
        debug_auto_table=debug_auto_table,
        customer_data=customer_data,
        available_tables=available_tables,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/checkout")
def checkout():
    """
    Checkout page for finalizing the order.
    Separated from the menu page for better UX and cleaner code organization.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    customer_data = get_current_user()
    return render_template(
        "checkout.html",
        debug_auto_table=debug_auto_table,
        customer_data=customer_data,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/menu-alt")
def menu_alt():
    """
    Alternative menu design with modern delivery app layout.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    customer_data = get_current_user()
    return render_template(
        "index-alt.html",
        debug_auto_table=debug_auto_table,
        customer_data=customer_data,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/feedback")
def feedback_form():
    """
    Feedback form for customers to rate their experience.

    Query params:
        - session_id: The dining session ID (optional, uses Flask session if available)
        - employee_id: The waiter/employee ID (optional)
    """
    # Try to get session_id from JWT first, then query param
    current_user = get_current_user()
    session_id_raw = (
        current_user.get("session_id") if current_user else None
    ) or request.args.get("session_id")
    employee_id_raw = request.args.get("employee_id")

    if not session_id_raw:
        return "Session ID requerido", 400

    try:
        session_id = UUID(str(session_id_raw))
    except (TypeError, ValueError):
        return "Session ID inválido", 400

    employee_id = None
    if employee_id_raw:
        try:
            employee_id = UUID(str(employee_id_raw))
        except (TypeError, ValueError):
            return "Employee ID inválido", 400

    # Verify session exists
    with get_session() as db_session:
        stmt = select(DiningSession).where(DiningSession.id == session_id)
        dining_session = db_session.execute(stmt).scalars().one_or_none()

        if not dining_session:
            return "Sesión no encontrada", 404

    return render_template(
        "feedback.html",
        session_id=str(session_id),
        employee_id=str(employee_id) if employee_id else "",
        feedback_api_base_url=current_app.config.get("EMPLOYEE_API_BASE_URL"),
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/kiosk/<location>")
def kiosk_screen(location: str):
    """
    Kiosk welcome screen for self-service ordering.

    Args:
        location: Kiosk location identifier (e.g., 'lobby', 'entrance')
    """
    return render_template(
        "kiosk.html",
        location=location,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.post("/kiosk/<location>/start")
def kiosk_start(location: str):
    """
    Auto-login for kiosk account.

    Creates or retrieves kiosk customer account for the location.
    Sets customer_ref in session.

    Security:
        - In production: requires PRONTO_KIOSK_SECRET header
        - In dev mode: no secret required
    """
    debug_mode = current_app.config.get("DEBUG_MODE", False)

    if _KIOSK_SECRET and not debug_mode:
        provided_secret = request.headers.get("X-PRONTO-KIOSK-SECRET", "")
        if provided_secret != _KIOSK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

    kiosk_email = f"kiosk+{location}@pronto.local"

    with get_session() as db:
        customer = get_customer_by_email(db, kiosk_email)

        if not customer:
            from pronto_shared.services.customer_service import create_customer

            try:
                customer = create_customer(
                    db,
                    first_name=f"Kiosk {location}",
                    email=kiosk_email,
                    password=_KIOSK_PASSWORD,
                    kind="kiosk",
                    kiosk_location=location,
                )
            except ValueError:
                customer = get_customer_by_email(db, kiosk_email)
                if not customer:
                    return jsonify({"error": "Failed to create kiosk account"}), 500

    try:
        customer_ref = customer_session_store.create_customer_ref(
            customer_id=customer["id"],
            email=customer["email"],
            name=customer["first_name"],
            kind="kiosk",
            kiosk_location=location,
        )
    except RedisUnavailableError:
        return jsonify({"error": "Service unavailable"}), 503

    session["customer_ref"] = customer_ref
    session.permanent = False

    return jsonify(
        {
            "success": True,
            "customer": {
                "id": customer["id"],
                "name": customer["first_name"],
                "kind": "kiosk",
                "location": location,
            },
        }
    )
