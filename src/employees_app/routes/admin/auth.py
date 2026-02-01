"""
Admin authentication routes using JWT.
"""

from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from shared.db import get_session
from shared.jwt_middleware import get_current_user
from shared.jwt_service import create_access_token, create_refresh_token
from shared.models import Employee
from shared.scope_guard import ScopeGuard
from shared.extensions import csrf

# Define blueprint
admin_bp = Blueprint(
    "admin_app", __name__, url_prefix="/admin", template_folder="../../templates/admin"
)


@admin_bp.before_request
def enforce_scope():
    return ScopeGuard(app_scope="admin", login_route="admin_app.login")()


@admin_bp.route("/logout")
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
            current_app.logger.error(f"Error signing out admin in DB: {e}")

    response = make_response(redirect(url_for("admin_app.login")))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@admin_bp.route("/system_login", methods=["GET", "POST"])
@csrf.exempt
def system_login():
    """System admin handoff endpoint for quick access."""
    if request.method == "GET":
        return render_template("login_admin.html", error="Método no permitido")

    raw_token = request.form.get("token")
    if not raw_token:
        return redirect(url_for("admin_app.login"))

    try:
        with get_session() as db_session:
            import hashlib
            import os
            from shared.models import AuditLog, SuperAdminHandoffToken
            from shared.datetime_utils import utcnow
            from shared.security import hash_identifier

            pepper = os.getenv("HANDOFF_PEPPER", "")
            token_hash = hashlib.sha256((raw_token + pepper).encode()).hexdigest()

            result = db_session.execute(
                update(SuperAdminHandoffToken)
                .where(
                    SuperAdminHandoffToken.token_hash == token_hash,
                    SuperAdminHandoffToken.target_scope == "admin",
                    SuperAdminHandoffToken.used_at.is_(None),
                    SuperAdminHandoffToken.expires_at > utcnow(),
                )
                .values(used_at=utcnow())
            )

            if result.rowcount != 1:
                db_session.rollback()
                current_app.logger.warning("Invalid handoff token attempt for admin scope")
                return redirect(url_for("admin_app.login"))

            token_record = (
                db_session.query(SuperAdminHandoffToken).filter_by(token_hash=token_hash).first()
            )

            if not token_record:
                db_session.rollback()
                return redirect(url_for("admin_app.login"))

            employee = db_session.query(Employee).filter_by(id=token_record.employee_id).first()

            if not employee or not employee.has_scope("admin"):
                db_session.rollback()
                return redirect(url_for("admin_app.login"))

            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=employee.email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope="admin",
            )
            refresh_token = create_refresh_token(employee_id=employee.id)

            audit = AuditLog(
                employee_id=employee.id,
                action="system_handoff_login",
                scope_from="system",
                scope_to="admin",
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
                f"System handoff successful: employee_id={employee.id}, scope=admin"
            )

            response = make_response(redirect(url_for("admin_app.dashboard")))
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
        current_app.logger.error(f"System login error (admin): {e}")
        return redirect(url_for("admin_app.login"))


@admin_bp.route("/login", methods=["GET"])
def login():
    user = get_current_user()
    if user and user.get("active_scope") == "admin":
        return redirect(url_for("admin_app.dashboard"))
    return render_template("login_admin.html")


@admin_bp.route("/login", methods=["POST"])
def process_login():
    email = request.form.get("email")
    password = request.form.get("password")

    try:
        with get_session() as db_session:
            from shared.security import hash_identifier

            email_hash = hash_identifier(email)
            employee = db_session.query(Employee).filter_by(email_hash=email_hash).first()

            if not employee or not employee.verify_password(password):
                return render_template("login_admin.html", error="Credenciales inválidas")

            # Role-based access control - strict check
            if not employee.has_scope("admin") and not employee.has_scope("system"):
                return render_template(
                    "login_admin.html", error="No tiene permisos de Administrador"
                )

            # Create JWT tokens
            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope="admin",
            )
            refresh_token = create_refresh_token(employee_id=employee.id)

            response = make_response(redirect(url_for("admin_app.dashboard")))
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
        return render_template("login_admin.html", error="Error de sistema")


@admin_bp.route("/dashboard")
def dashboard():
    """
    Admin dashboard - shows all sections including reports, config, etc.
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
    employee_role = user.get("employee_role", "admin") if user else "admin"
    employee_id = user.get("employee_id") if user else None
    employee_name = user.get("employee_name") if user else None

    # Load core data
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

    return render_template(
        "dashboard.html",
        app_context="Admin",
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
        kitchen_orders=[],
        session_orders=session_orders_data,
        currency=get_config_value("currency_code", "USD"),
        currency_symbol=get_config_value("currency_symbol", "$"),
    )
