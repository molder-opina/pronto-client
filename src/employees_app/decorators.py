"""Decorators for route protection and authentication using JWT."""

from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import jsonify, redirect, url_for

from shared.auth.service import Roles
from shared.jwt_middleware import get_current_user


def _has_role(user: dict, required_role: str) -> bool:
    """
    Check if user has the required role.

    Checks both primary role and additional_roles from JWT.

    Args:
        user: JWT payload dict
        required_role: The role to check for

    Returns:
        True if user has the role (either as primary or additional)
    """
    if not user:
        return False

    # Check primary role
    employee_role = user.get("employee_role")
    if employee_role == required_role:
        return True

    # Check additional roles
    additional_roles = user.get("employee_additional_roles")
    if additional_roles and isinstance(additional_roles, list):
        if required_role in additional_roles:
            return True

    return False


def login_required(f):
    """Decorator to require JWT authentication for a route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.get("employee_id"):
            return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED
        return f(*args, **kwargs)

    return decorated_function


def web_login_required(f):
    """Decorator to require authentication for web routes (redirects to login)."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.get("employee_id"):
            from flask import request

            return redirect(url_for("auth.login_page", next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Decorator to require admin role for a route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.get("employee_id"):
            return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED

        employee_role = user.get("employee_role")
        if employee_role not in {Roles.SUPER_ADMIN, Roles.ADMIN}:
            return jsonify(
                {"error": "Se requieren permisos de administrador"}
            ), HTTPStatus.FORBIDDEN

        return f(*args, **kwargs)

    return decorated_function


def web_admin_required(f):
    """Decorator to require admin role for web routes (redirects with flash)."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.get("employee_id"):
            from flask import request

            return redirect(url_for("auth.login_page", next=request.url))

        employee_role = user.get("employee_role")
        if employee_role not in {Roles.SUPER_ADMIN, Roles.ADMIN}:
            return redirect(url_for("employee_dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def role_required(required_roles):
    """
    Decorator factory to require specific role(s) for a route.

    Checks both primary role and additional_roles to support multi-role employees.
    For example, a waiter with additional_roles='["cashier"]' can access cashier endpoints.

    Args:
        required_roles: Can be a single role (str) or list of roles (list[str])
    """
    # Normalize to list for consistent handling
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user or not user.get("employee_id"):
                return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED

            # Super admin can access everything
            employee_role = user.get("employee_role")
            if employee_role == Roles.SUPER_ADMIN:
                return f(*args, **kwargs)

            # Check if employee has any of the required roles (primary or additional)
            has_required_role = any(_has_role(user, role) for role in required_roles)
            if not has_required_role:
                roles_str = ", ".join(required_roles)
                return jsonify(
                    {"error": f"Se requiere uno de estos roles: {roles_str}"}
                ), HTTPStatus.FORBIDDEN

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def web_role_required(required_roles: list[str]):
    """
    Decorator factory to require specific roles for web routes.

    Checks both primary role and additional_roles to support multi-role employees.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user or not user.get("employee_id"):
                from flask import request

                return redirect(url_for("auth.login_page", next=request.url))

            # Super admin can access everything
            employee_role = user.get("employee_role")
            if employee_role == Roles.SUPER_ADMIN:
                return f(*args, **kwargs)

            # Check if employee has any of the required roles (primary or additional)
            has_required_role = any(_has_role(user, role) for role in required_roles)
            if not has_required_role:
                return redirect(url_for("employee_dashboard.dashboard"))

            return f(*args, **kwargs)

        return decorated_function

    return decorator
