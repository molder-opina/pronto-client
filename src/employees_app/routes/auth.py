"""
Authentication routes for employee portal (web forms).
Uses JWT for authentication.
"""

from __future__ import annotations

import logging
import re

from flask import (
    Blueprint,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from shared.constants import OrderStatus
from shared.db import get_session
from shared.jwt_middleware import get_current_user
from shared.jwt_service import create_access_token, create_refresh_token
from shared.models import Employee, Order
from shared.security import verify_credentials
from shared.security_middleware import rate_limit

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


@auth_bp.get("/api/stats/public")
def public_stats():
    """Get public stats for login page."""
    try:
        with get_session() as db:
            active_orders = (
                db.query(Order)
                .filter(
                    Order.workflow_status.notin_(
                        [OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value]
                    )
                )
                .count()
            )

        return {"active_orders": active_orders}
    except Exception as e:
        logger.error(f"Error getting public stats: {e}")
        return {"active_orders": 0}


@auth_bp.get("/login")
def login_page():
    """Redirect to console selector instead of showing generic login."""
    return redirect("/")


@auth_bp.post("/login")
@rate_limit(max_requests=5, window_seconds=300)
def login():
    """
    Process login form and issue JWT tokens.

    Security features:
    - Rate limiting: 5 attempts per 5 minutes
    - Email format validation
    - Password timing-attack resistant verification
    """
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    logger.info(f"Login attempt for email: {email}")

    # Validate inputs
    if not email or not password:
        logger.warning("Login failed: Missing credentials")
        return redirect(url_for("auth.login_page"))

    # Validate email format
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_regex, email):
        logger.warning(f"Login failed: Invalid email format for {email}")
        return redirect(url_for("auth.login_page"))

    # Validate password length
    if len(password) < 8 or len(password) > 128:
        logger.warning("Login failed: Invalid password length")
        return redirect(url_for("auth.login_page"))

    with get_session() as db:
        # Find employee by email
        from shared.security import hash_identifier

        email_hash = hash_identifier(email)

        # Query using email hash
        employee = db.query(Employee).filter(Employee.email_hash == email_hash).first()

        if not employee:
            logger.warning(f"Login failed: No employee found for email {email}")
            return redirect(url_for("auth.login_page"))

        # Verify password
        if not verify_credentials(email, password, employee.auth_hash):
            logger.warning(f"Login failed: Invalid password for {email}")
            return redirect(url_for("auth.login_page"))

        # Check if employee is active
        if not employee.is_active:
            logger.warning(f"Login failed: Inactive account for {email}")
            return redirect(url_for("auth.login_page"))

        # Sign in employee (registro de firma)
        employee.sign_in()
        db.commit()

        # Determine scope based on role
        if employee.role == "chef":
            active_scope = "chef"
        elif employee.role == "waiter":
            active_scope = "waiter"
        elif employee.role == "cashier":
            active_scope = "cashier"
        elif employee.role in ["system", "super_admin"]:
            active_scope = "system"
        else:
            active_scope = "admin"

        # Create JWT tokens
        access_token = create_access_token(
            employee_id=employee.id,
            employee_name=employee.name,
            employee_email=employee.email,
            employee_role=employee.role,
            employee_additional_roles=employee.additional_roles,
            active_scope=active_scope,
        )
        refresh_token = create_refresh_token(employee_id=employee.id)

        logger.info(
            f"Login successful: Employee {employee.name} (ID: {employee.id}, Role: {employee.role}) signed in"
        )

        # Determine redirect URL
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            redirect_url = next_url
        elif employee.role == "chef":
            redirect_url = url_for("employee_dashboard.dashboard") + "?context=chef"
        elif employee.role == "waiter":
            redirect_url = url_for("employee_dashboard.dashboard") + "?context=waiter"
        elif employee.role == "cashier":
            redirect_url = url_for("employee_dashboard.dashboard") + "?context=cashier"
        else:
            redirect_url = url_for("employee_dashboard.dashboard")

        # Create response with JWT cookies
        response = make_response(redirect(redirect_url))
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


@auth_bp.post("/logout")
def logout():
    """Logout employee - clears JWT cookies."""
    user = get_current_user()
    if user:
        try:
            with get_session() as db:
                employee = db.query(Employee).filter(Employee.id == user.get("employee_id")).first()
                if employee:
                    employee.sign_out()
                    db.commit()
        except Exception as e:
            logger.error(f"Error signing out employee in DB: {e}")

    response = make_response(redirect("/"))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@auth_bp.get("/logout")
def logout_get():
    """Logout via GET - clears JWT cookies."""
    user = get_current_user()
    if user:
        try:
            with get_session() as db:
                employee = db.query(Employee).filter(Employee.id == user.get("employee_id")).first()
                if employee:
                    employee.sign_out()
                    db.commit()
        except Exception as e:
            logger.error(f"Error signing out employee in DB: {e}")

    response = make_response(redirect("/"))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@auth_bp.get("/authorization-error")
def authorization_error():
    """Show authorization error page."""
    code = request.args.get("code", "403")
    message = request.args.get("message", "No tienes permiso para acceder a este recurso.")
    from_url = request.args.get("from", "")
    return render_template(
        "authorization_error.html", code=code, message=message, from_url=from_url
    )
