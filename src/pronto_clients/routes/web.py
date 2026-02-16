"""
Customer facing web views rendered via Jinja templates.
"""

from __future__ import annotations

import os
from flask import Blueprint, current_app, render_template, request, session, jsonify
from sqlalchemy import select

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
            current_app.logger.error(f"Error fetching tables for debug: {e}")

    return render_template(
        "index.html",
        debug_auto_table=debug_auto_table,
        customer_data=customer_data,
        available_tables=available_tables,
        api_base_url=current_app.config.get("API_BASE_URL", "http://localhost:6082"),
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
        api_base_url=current_app.config.get("API_BASE_URL", "http://localhost:6082"),
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
        api_base_url=current_app.config.get("API_BASE_URL", "http://localhost:6082"),
    )


# DISABLED: Users are redirected to Orders tab instead of thank you page
# @web_bp.get("/thanks")
# def thank_you():
#     """
#     Thank you page shown after completing an order, with order history.
#     """
#     # Try to get session_id from Flask session first, then query param (backwards compatibility)
#     session_id = session.get("dining_session_id") or request.args.get("session_id", type=int)
#
#     current_app.logger.info(f"[THANK YOU PAGE] Session ID from Flask session: {session.get('dining_session_id')}")
#     current_app.logger.info(f"[THANK YOU PAGE] Session ID from URL: {request.args.get('session_id')}")
#     current_app.logger.info(f"[THANK YOU PAGE] Using session_id: {session_id}")
#
#     orders = []
#     session_data = None
#
#     can_pay_digitally = False
#
#     if session_id:
#         try:
#             with get_session() as db_session:
#                 # Fetch the dining session with all orders (regardless of status)
#                 # After placing an order, the user should always see their order
#                 stmt = (
#                     select(DiningSession)
#                     .where(DiningSession.id == session_id)
#                 )
#                 dining_session = db_session.execute(stmt).scalars().first()
#
#                 current_app.logger.info(f"[THANK YOU PAGE] Found dining_session: {dining_session is not None}")
#
#                 if dining_session:
#                     current_app.logger.info(f"[THANK YOU PAGE] Session ID: {dining_session.id}, Status: {dining_session.status}, Orders count: {len(dining_session.orders)}")
#                     session_data = {
#                         "id": dining_session.id,
#                         "table_number": dining_session.table_number,
#                         "subtotal": float(dining_session.subtotal),
#                         "tax_amount": float(dining_session.tax_amount),
#                         "total_amount": float(dining_session.total_amount),
#                     }
#                     customer = dining_session.customer
#                     if customer and customer.email:
#                         can_pay_digitally = not customer.email.startswith("anonimo+")
#
#                     # Fetch all orders in this session
#                     for order in dining_session.orders:
#                         order_items = []
#                         for item in order.items:
#                             # Build modifiers list
#                             modifiers = []
#                             for modifier in item.modifiers:
#                                 modifiers.append({
#                                     "name": modifier.modifier.name,
#                                     "price": float(modifier.modifier.price) if modifier.modifier.price else 0.0
#                                 })
#
#                             order_items.append({
#                                 "name": item.menu_item.name,
#                                 "quantity": item.quantity,
#                                 "unit_price": float(item.unit_price),
#                                 "total": float(item.unit_price * item.quantity),
#                                 "modifiers": modifiers,
#                             })
#
#                         orders.append({
#                             "id": order.id,
#                             "status": order.workflow_status,
#                             "items": order_items,
#                             "subtotal": float(order.subtotal),
#                             "tax_amount": float(order.tax_amount),
#                             "total_amount": float(order.total_amount),
#                             "created_at": order.created_at,
#                         })
#         except Exception as e:
#             current_app.logger.error(f"[THANK YOU PAGE] Error loading session: {e}")
#             # Continue rendering without session info rather than crashing
#
#     current_app.logger.info(f"[THANK YOU PAGE] Rendering template with session={session_data is not None}, orders count={len(orders)}")
#
#     # Debug: Log the type and structure of orders
#     if orders:
#         current_app.logger.info(f"[THANK YOU PAGE] First order type: {type(orders[0])}")
#         current_app.logger.info(f"[THANK YOU PAGE] First order keys: {orders[0].keys() if isinstance(orders[0], dict) else 'NOT A DICT'}")
#         if isinstance(orders[0], dict) and 'items' in orders[0]:
#             current_app.logger.info(f"[THANK YOU PAGE] First order items type: {type(orders[0]['items'])}")
#
#     return render_template(
#         "thank_you.html",
#         session=session_data,
#         orders=orders,
#         show_estimated_time=True,
#         estimated_time_min=15,
#         estimated_time_max=25,
#         config=current_app.config,
#         can_pay_digitally=can_pay_digitally,
#     )


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
    session_id = (
        current_user.get("session_id") if current_user else None
    ) or request.args.get("session_id", type=int)
    employee_id = request.args.get("employee_id", type=int)

    if not session_id:
        return "Session ID requerido", 400

    # Verify session exists
    with get_session() as db_session:
        stmt = select(DiningSession).where(DiningSession.id == session_id)
        dining_session = db_session.execute(stmt).scalars().one_or_none()

        if not dining_session:
            return "Sesión no encontrada", 404

    return render_template(
        "feedback.html",
        session_id=session_id,
        employee_id=employee_id,
        feedback_api_base_url=current_app.config.get("EMPLOYEE_API_BASE_URL"),
        api_base_url=current_app.config.get("API_BASE_URL", "http://localhost:6082"),
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
        api_base_url=current_app.config.get("API_BASE_URL", "http://localhost:6082"),
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
                    password="kiosk-no-auth",
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
