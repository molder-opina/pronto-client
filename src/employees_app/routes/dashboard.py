"""
Server-rendered views for the employee portal.
Uses JWT for authentication.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, redirect, render_template, url_for
from sqlalchemy import select

from employees_app.decorators import web_admin_required, web_login_required, web_role_required
from shared.auth.service import Roles
from shared.constants import OrderStatus, SessionStatus
from shared.jwt_middleware import get_current_user
from shared.permissions import Permission, get_user_permissions, has_permission
from shared.services.business_config_service import get_config_value
from shared.services.day_period_service import DayPeriodService
from shared.services.menu_service import list_menu
from shared.services.order_service import get_dashboard_metrics, get_waiter_tips, list_orders
from shared.services.role_service import (
    list_employees_by_permission,
    list_employees_with_permissions,
)
from shared.services.settings_service import get_setting

dashboard_bp = Blueprint("employee_dashboard", __name__)
logger = logging.getLogger(__name__)


def console_selector():
    """
    Console selection page - shown when accessing root without context.
    Allows users to choose which console/app they want to use.
    """
    return render_template(
        "console_selector.html",
        employee_name="Usuario",
        employee_role="guest",
    )


@dashboard_bp.get("/")
def dashboard():
    """
    Console selector page - always shown at root URL.
    """
    return console_selector()


@dashboard_bp.get("/dashboard")
@web_login_required
def contextual_dashboard():
    """
    Contextual dashboard based on URL parameters or JWT scope.
    """
    from flask import request

    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login_page"))

    # Get context from URL or JWT
    context = request.args.get("context") or user.get("active_scope", "admin")

    # Get employee info from JWT
    employee_role = user.get("employee_role")
    employee_id = user.get("employee_id")
    employee_name = user.get("employee_name")

    # Load core data
    metrics = get_dashboard_metrics()
    orders_result = list_orders(include_delivered=True)

    logger.info(
        f"[DASHBOARD DEBUG] Total orders from list_orders: {len(orders_result.get('orders', []))}"
    )

    session_orders = [
        order
        for order in orders_result["orders"]
        if order["session"]["status"] != SessionStatus.PAID.value
    ]
    orders = [
        order for order in session_orders if order["workflow_status"] != OrderStatus.DELIVERED.value
    ]

    logger.info(f"[DASHBOARD DEBUG] session_orders after PAID filter: {len(session_orders)}")
    logger.info(f"[DASHBOARD DEBUG] orders after DELIVERED filter: {len(orders)}")

    menu_data = list_menu()
    day_periods = DayPeriodService.list_periods()
    employees = list_employees_with_permissions()

    # Only load waiter/chef data if user has permission
    waiters = []
    chefs = []
    waiter_orders = []
    kitchen_orders = []

    if employee_role in ["system", "admin_roles", "waiter", "cashier"]:
        from datetime import datetime, timedelta

        waiters = list_employees_by_permission("waiter-board")

        paid_window_minutes = int(get_config_value("paid_orders_window_minutes", 15) or 15)

        waiter_orders = []
        for order in session_orders:
            session_status = order["session"]["status"]

            if session_status == SessionStatus.PAID.value:
                continue

            waiter_orders.append(order)

        logger.info(
            f"[DASHBOARD DEBUG waiter_orders] Final waiter_orders count: {len(waiter_orders)}"
        )

    if waiter_orders:
        first_order = waiter_orders[0]
        current_app.logger.info(
            f"[DASHBOARD DEBUG] First waiter order ID: {first_order.get('id')}, Items count: {len(first_order.get('items', []))}"
        )

    if employee_role in ["system", "admin_roles", "chef"]:
        chefs = list_employees_by_permission("kitchen-board")
        kitchen_orders = [
            order
            for order in orders
            if order.get("requires_kitchen")
            and order["workflow_status"]
            in {
                OrderStatus.QUEUED.value,
                OrderStatus.PREPARING.value,
                OrderStatus.READY.value,
            }
        ]

    can_process_payments = has_permission(employee_role, Permission.PAYMENTS_PROCESS)
    role_capabilities = get_user_permissions(employee_role)

    items_per_page = get_config_value("items_per_page", 10)
    paid_orders_retention_minutes = int(get_config_value("paid_orders_retention_minutes", 60) or 60)
    payment_action_delay_seconds = int(get_config_value("payment_action_delay_seconds", 5) or 5)
    table_base_prefix = (get_setting("table_base_prefix", "M") or "M").strip().upper()[:3]

    app_context = context

    # Select appropriate template based on context
    template_map = {
        "waiter": "dashboard_waiter.html",
        "chef": "dashboard_chef.html",
        "cashier": "dashboard_cashier.html",
        "admin": "dashboard_admin.html",
        "system": "dashboard_admin.html",
    }
    template_name = template_map.get(context, "dashboard.html")

    return render_template(
        template_name,
        app_context=app_context,
        metrics=metrics,
        orders=orders,
        menu=menu_data,
        employees=employees,
        day_periods=day_periods,
        employee_role=employee_role,
        employee_id=employee_id,
        employee_name=employee_name,
        waiters=waiters,
        chefs=chefs,
        waiter_orders=waiter_orders,
        kitchen_orders=kitchen_orders,
        session_orders=session_orders,
        items_per_page=items_per_page,
        can_process_payments=can_process_payments,
        role_capabilities=role_capabilities,
        paid_orders_retention_minutes=paid_orders_retention_minutes,
        payment_action_delay_seconds=payment_action_delay_seconds,
        table_base_prefix=table_base_prefix,
    )


@dashboard_bp.get("/waiter")
@web_login_required
def waiter_dashboard():
    """
    Dedicated waiter dashboard page.
    """
    return redirect(url_for("employee_dashboard.contextual_dashboard") + "?context=waiter")


@dashboard_bp.get("/kitchen")
@web_role_required([Roles.SUPER_ADMIN, Roles.CHEF])
def kitchen_board():
    """
    DEPRECATED: Kitchen board has been integrated into the main dashboard.
    """
    return redirect(url_for("employee_dashboard.contextual_dashboard") + "#panel-cocina")


@dashboard_bp.get("/operation/kitchen")
@dashboard_bp.get("/operation/cocina")
@web_role_required([Roles.SUPER_ADMIN, Roles.CHEF])
def kitchen_board_alias():
    """
    Compatibility aliases for kitchen board deep links.
    """
    return redirect(url_for("employee_dashboard.contextual_dashboard") + "#panel-cocina")


@dashboard_bp.get("/tips/<int:employee_id>")
@web_login_required
def employee_tips(employee_id: int):
    """View for employees to see their tips."""
    tips_data = get_waiter_tips(employee_id)
    if "error" in tips_data:
        return render_template("error.html", error=tips_data["error"]), 404
    return render_template("tips.html", tips=tips_data)


@dashboard_bp.get("/business-config")
@web_admin_required
def business_config():
    """
    Business configuration page - accessible only by admins.
    """
    from shared.db import get_session
    from shared.models import KeyboardShortcut

    user = get_current_user()

    with get_session() as db_session:
        shortcuts = (
            db_session.execute(
                select(KeyboardShortcut).order_by(
                    KeyboardShortcut.sort_order, KeyboardShortcut.category
                )
            )
            .scalars()
            .all()
        )

    shortcuts_data = [
        {
            "id": s.id,
            "combo": s.combo,
            "description": s.description,
            "category": s.category,
            "callback_function": s.callback_function,
            "is_enabled": s.is_enabled,
            "prevent_default": s.prevent_default,
            "sort_order": s.sort_order,
        }
        for s in shortcuts
    ]

    return render_template(
        "business_config.html",
        employee_role=user.get("employee_role") if user else None,
        employee_id=user.get("employee_id") if user else None,
        employee_name=user.get("employee_name") if user else None,
        shortcuts=shortcuts_data,
    )


@dashboard_bp.get("/roles-management")
@web_admin_required
def roles_management():
    """
    Custom roles management page - accessible only by admins.
    """
    user = get_current_user()
    return render_template(
        "roles_management.html",
        employee_role=user.get("employee_role") if user else None,
        employee_id=user.get("employee_id") if user else None,
        employee_name=user.get("employee_name") if user else None,
    )


@dashboard_bp.get("/feedback-dashboard")
@web_admin_required
def feedback_dashboard():
    """
    Feedback dashboard - accessible only by admins.
    """
    user = get_current_user()
    return render_template(
        "feedback_dashboard.html",
        employee_role=user.get("employee_role") if user else None,
        employee_id=user.get("employee_id") if user else None,
        employee_name=user.get("employee_name") if user else None,
    )


@dashboard_bp.get("/analytics")
@web_admin_required
def analytics():
    """
    Analytics dashboard - accessible only by admins.
    """
    user = get_current_user()
    return render_template(
        "analytics.html",
        employee_role=user.get("employee_role") if user else None,
        employee_id=user.get("employee_id") if user else None,
        employee_name=user.get("employee_name") if user else None,
    )


@dashboard_bp.get("/branding")
@web_admin_required
def branding():
    """
    Branding management page - accessible only by admins.
    """
    user = get_current_user()
    return render_template(
        "branding.html",
        employee_role=user.get("employee_role") if user else None,
        employee_id=user.get("employee_id") if user else None,
        employee_name=user.get("employee_name") if user else None,
        restaurant_name=current_app.config.get("RESTAURANT_NAME", "Restaurante"),
    )


@dashboard_bp.get("/order/<int:order_id>")
@web_login_required
def order_detail(order_id: int):
    """
    Detailed view of a specific order.
    """
    from sqlalchemy.orm import joinedload

    from shared.db import get_session
    from shared.models import Order, OrderItem, OrderItemModifier

    user = get_current_user()

    with get_session() as db_session:
        order = (
            db_session.query(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.menu_item),
                joinedload(Order.items)
                .joinedload(OrderItem.modifiers)
                .joinedload(OrderItemModifier.modifier),
                joinedload(Order.session),
                joinedload(Order.customer),
                joinedload(Order.waiter),
                joinedload(Order.chef),
                joinedload(Order.delivery_waiter),
            )
            .filter(Order.id == order_id)
            .first()
        )

        if not order:
            return render_template("error.html", error="Orden no encontrada"), 404

        order_data = {
            "id": order.id,
            "session_id": order.session_id,
            "workflow_status": order.workflow_status,
            "created_at": order.created_at,
            "waiter_accepted_at": order.waiter_accepted_at,
            "chef_accepted_at": order.chef_accepted_at,
            "ready_at": order.ready_at,
            "delivered_at": order.delivered_at,
            "total_amount": order.total_amount,
            "notes": order.notes,
            "customer_id": order.customer_id,
            "session": {"table_number": order.session.table_number if order.session else None},
            "line_items": [],
        }

        for item in order.items:
            item_data = {
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "special_instructions": item.special_instructions,
                "menu_item": {"name": item.menu_item.name if item.menu_item else "Unknown"},
                "modifiers": [],
            }
            for mod in item.modifiers:
                if mod.modifier:
                    item_data["modifiers"].append(
                        {"modifier": {"name": mod.modifier.name}, "quantity": mod.quantity}
                    )
            order_data["line_items"].append(item_data)

        return render_template(
            "order_detail.html",
            order=order_data,
            employee_role=user.get("employee_role") if user else None,
            employee_name=user.get("employee_name") if user else None,
        )


@dashboard_bp.get("/error-catalog")
@web_admin_required
def error_catalog():
    """Display system error catalog and service info."""
    from shared.error_catalog import ERROR_CATALOG, SERVICE_INFO_6081

    return render_template(
        "error_catalog.html", catalog=ERROR_CATALOG, service_info=SERVICE_INFO_6081
    )
