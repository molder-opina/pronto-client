"""
Chef authentication routes using JWT.
"""

import hashlib
import os

from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import update

from shared.extensions import csrf
from shared.datetime_utils import utcnow
from shared.db import get_session
from shared.jwt_middleware import get_current_user
from shared.jwt_service import create_access_token, create_refresh_token
from shared.models import AuditLog, Employee, SuperAdminHandoffToken
from shared.scope_guard import ScopeGuard

chef_bp = Blueprint(
    "chef_app", __name__, url_prefix="/chef", template_folder="../../templates/chef"
)


@chef_bp.before_request
def chef_guard():
    return ScopeGuard(app_scope="chef", login_route="chef_app.login")()


@chef_bp.route("/logout")
def logout():
    user = get_current_user()
    if user:
        try:
            with get_session() as db:
                employee = db.query(Employee).filter(Employee.id == user.get("employee_id")).first()
                if employee:
                    employee.sign_out()
                    db.commit()
        except Exception as e:
            current_app.logger.error(f"Error signing out chef in DB: {e}")

    response = make_response(redirect(url_for("chef_app.login")))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@chef_bp.route("/login", methods=["GET"])
def login():
    user = get_current_user()
    if user and user.get("active_scope") == "chef":
        return redirect(url_for("chef_app.dashboard"))
    return render_template("login_chef.html")


@chef_bp.route("/login", methods=["POST"], endpoint="process_login")
def process_login():
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return render_template("login_chef.html", error="Credenciales requeridas")

    try:
        with get_session() as db_session:
            from datetime import UTC
            from shared.security import hash_identifier

            email_hash = hash_identifier(email)
            employee = db_session.query(Employee).filter_by(email_hash=email_hash).first()

            if not employee or not employee.verify_password(password):
                return render_template("login_chef.html", error="Credenciales inválidas")

            if not employee.has_scope("chef"):
                return render_template("login_chef.html", error="No tiene permisos de Cocina")

            # Create JWT tokens
            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope="chef",
            )
            refresh_token = create_refresh_token(employee_id=employee.id)

            # Update last login timestamp
            employee.last_activity_at = utcnow()
            db_session.commit()

            response = make_response(redirect(url_for("chef_app.dashboard")))
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=86400,
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=604800,
                path="/",
            )
            return response

    except Exception as e:
        current_app.logger.error(f"Login error: {e}")
        return render_template("login_chef.html", error="Error de sistema")


@chef_bp.route("/dashboard")
def dashboard():
    """
    Chef dashboard - shows KDS (Kitchen Display System).
    """
    from shared.constants import OrderStatus, SessionStatus
    from shared.services.business_config_service import get_config_value
    from shared.services.day_period_service import DayPeriodService
    from shared.services.menu_service import list_menu
    from shared.services.order_service import get_dashboard_metrics, list_orders
    from shared.services.role_service import (
        list_employees_by_permission,
        list_employees_with_permissions,
    )

    user = get_current_user()
    employee_role = user.get("employee_role", "chef") if user else "chef"
    employee_id = user.get("employee_id") if user else None
    employee_name = user.get("employee_name") if user else None

    metrics = get_dashboard_metrics()
    orders_result = list_orders(include_delivered=True)
    session_orders_data = [
        order
        for order in orders_result["orders"]
        if order["session"]["status"] != SessionStatus.PAID.value
    ]
    orders_data = [
        order
        for order in session_orders_data
        if order["workflow_status"] != OrderStatus.DELIVERED.value
    ]
    menu_data = list_menu()
    day_periods = DayPeriodService.list_periods()
    employees = list_employees_with_permissions()

    kitchen_orders = [
        order
        for order in orders_data
        if order.get("requires_kitchen")
        and order["workflow_status"]
        in {
            OrderStatus.QUEUED.value,
            OrderStatus.PREPARING.value,
            OrderStatus.READY.value,
        }
    ]

    # Get role capabilities for chef
    role_capabilities = {
        "can_accept_orders": False,
        "can_deliver_orders": False,
        "can_cancel_orders": False,
        "can_edit_orders": False,
        "can_move_tables": False,
        "can_process_payments": False,
        "can_reprint_tickets": False,
        "can_advance_kitchen": True,
    }

    # Get configuration values for dashboard
    paid_orders_retention = int(get_config_value("paid_orders_retention_minutes", 30))
    payment_action_delay = int(get_config_value("payment_action_delay_seconds", 3))
    table_prefix = get_config_value("table_base_prefix", "M")
    items_per_page = int(get_config_value("items_per_page", 20))

    return render_template(
        "dashboard.html",
        app_context="Chef",
        metrics=metrics,
        orders=orders_data,
        menu=menu_data,
        employees=employees,
        day_periods=day_periods,
        employee_role=employee_role,
        employee_id=employee_id,
        employee_name=employee_name,
        waiters=list_employees_by_permission("waiter-board"),
        chefs=list_employees_by_permission("kitchen-board"),
        waiter_orders=[],
        kitchen_orders=kitchen_orders,
        session_orders=session_orders_data,
        currency=get_config_value("currency_code", "USD"),
        currency_symbol=get_config_value("currency_symbol", "$"),
        role_capabilities=role_capabilities,
        can_process_payments=False,
        paid_orders_retention_minutes=paid_orders_retention,
        payment_action_delay_seconds=payment_action_delay,
        table_base_prefix=table_prefix,
        items_per_page=items_per_page,
    )


@chef_bp.route("/kds")
def kds():
    """Kitchen Display System - redirects to dashboard."""
    return redirect(url_for("chef_app.dashboard"))


@chef_bp.route("/system_login", methods=["GET", "POST"])
@csrf.exempt
def system_login():
    """System admin handoff endpoint for quick access."""
    if request.method == "GET":
        return render_template("login_chef.html", error="Método no permitido")

    raw_token = request.form.get("token")
    if not raw_token:
        return redirect(url_for("chef_app.login"))

    try:
        with get_session() as db_session:
            pepper = os.getenv("HANDOFF_PEPPER", "")
            token_hash = hashlib.sha256((raw_token + pepper).encode()).hexdigest()

            result = db_session.execute(
                update(SuperAdminHandoffToken)
                .where(
                    SuperAdminHandoffToken.token_hash == token_hash,
                    SuperAdminHandoffToken.target_scope == "chef",
                    SuperAdminHandoffToken.used_at.is_(None),
                    SuperAdminHandoffToken.expires_at > utcnow(),
                )
                .values(used_at=utcnow())
            )

            if result.rowcount != 1:
                db_session.rollback()
                current_app.logger.warning("Invalid handoff token attempt for chef scope")
                return redirect(url_for("chef_app.login"))

            token_record = (
                db_session.query(SuperAdminHandoffToken).filter_by(token_hash=token_hash).first()
            )

            if not token_record:
                db_session.rollback()
                return redirect(url_for("chef_app.login"))

            employee = db_session.query(Employee).filter_by(id=token_record.employee_id).first()

            if not employee or not employee.has_scope("chef"):
                db_session.rollback()
                return redirect(url_for("chef_app.login"))

            # Create JWT tokens
            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=employee.email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope="chef",
            )
            refresh_token = create_refresh_token(employee_id=employee.id)

            audit = AuditLog(
                employee_id=employee.id,
                action="system_handoff_login",
                scope_from="system",
                scope_to="chef",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
                token_id=token_record.id,
            )
            db_session.add(audit)

            employee.last_activity_at = utcnow()

            try:
                db_session.commit()
            except Exception as commit_error:
                current_app.logger.error(f"Commit failed in system_login: {commit_error}")
                raise

            current_app.logger.info(
                f"System handoff successful: employee_id={employee.id}, scope=chef"
            )

            response = make_response(redirect(url_for("chef_app.dashboard")))
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=86400,
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=604800,
                path="/",
            )
            return response

    except Exception as e:
        current_app.logger.error(f"System login error (chef): {e}")
        return redirect(url_for("chef_app.login"))
