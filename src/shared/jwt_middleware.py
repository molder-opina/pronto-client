"""
JWT Middleware for Flask.

Provides request-level JWT validation and user context injection.
Replaces Flask-Session based authentication.
"""

from __future__ import annotations

import logging
from functools import wraps
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from flask import g, jsonify, request

from shared.jwt_service import (
    InvalidTokenError,
    JWTError,
    TokenExpiredError,
    decode_token,
    extract_token_from_request,
)

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


def init_jwt_middleware(app: Flask) -> None:
    """
    Initialize JWT middleware for a Flask app.

    Sets up before_request handler to:
    1. Extract JWT from request
    2. Validate token
    3. Store user info in g.current_user

    Args:
        app: Flask application instance
    """

    @app.before_request
    def load_jwt_user():
        """Load user from JWT token into Flask g object."""
        g.current_user = None
        g.jwt_token = None

        token = extract_token_from_request(request)
        if not token:
            return

        try:
            payload = decode_token(token, verify_type="access")
            g.current_user = payload
            g.jwt_token = token
        except TokenExpiredError:
            # Token expired - don't set user, let route decorators handle
            logger.debug(f"Expired token on {request.path}")
        except InvalidTokenError as e:
            logger.warning(f"Invalid token on {request.path}: {e}")


def get_current_user() -> dict[str, Any] | None:
    """
    Get current authenticated user from request context.

    Returns:
        User payload dict if authenticated, None otherwise
    """
    return getattr(g, "current_user", None)


def get_employee_id() -> int | None:
    """Get current employee ID from JWT."""
    user = get_current_user()
    return user.get("employee_id") if user else None


def get_employee_role() -> str | None:
    """Get current employee role from JWT."""
    user = get_current_user()
    return user.get("employee_role") if user else None


def get_active_scope() -> str | None:
    """Get current active scope from JWT."""
    user = get_current_user()
    return user.get("active_scope") if user else None


def jwt_required(f):
    """
    Decorator to require valid JWT for a route.

    Returns 401 if no valid token present.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED
        return f(*args, **kwargs)

    return decorated_function


def jwt_optional(f):
    """
    Decorator that allows JWT but doesn't require it.

    Sets g.current_user if token present, None otherwise.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # User is already loaded by middleware, just continue
        return f(*args, **kwargs)

    return decorated_function


def scope_required(required_scope: str):
    """
    Decorator factory to require specific scope in JWT.

    Args:
        required_scope: Required scope (waiter, chef, cashier, admin)

    Returns:
        Decorator that validates scope
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED

            active_scope = user.get("active_scope")
            if active_scope != required_scope:
                logger.warning(
                    f"Scope mismatch: required={required_scope}, "
                    f"active={active_scope}, path={request.path}"
                )
                return jsonify(
                    {
                        "error": f"Scope mismatch: requires {required_scope}, but token is {active_scope}",
                        "code": "SCOPE_MISMATCH",
                    }
                ), HTTPStatus.FORBIDDEN

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def role_required(required_roles: str | list[str]):
    """
    Decorator factory to require specific role(s) in JWT.

    Args:
        required_roles: Required role(s)

    Returns:
        Decorator that validates role
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED

            # Super admin bypass
            employee_role = user.get("employee_role")
            if employee_role == "super_admin":
                return f(*args, **kwargs)

            # Check primary role
            if employee_role in required_roles:
                return f(*args, **kwargs)

            # Check additional roles
            additional_roles = user.get("employee_additional_roles") or []
            if any(role in required_roles for role in additional_roles):
                return f(*args, **kwargs)

            roles_str = ", ".join(required_roles)
            return jsonify(
                {"error": f"Se requiere uno de estos roles: {roles_str}"}
            ), HTTPStatus.FORBIDDEN

        return decorated_function

    return decorator


def admin_required(f):
    """Decorator to require admin role."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Autenticacion requerida"}), HTTPStatus.UNAUTHORIZED

        employee_role = user.get("employee_role")
        if employee_role not in {"super_admin", "admin"}:
            return jsonify(
                {"error": "Se requieren permisos de administrador"}
            ), HTTPStatus.FORBIDDEN

        return f(*args, **kwargs)

    return decorated_function


def validate_api_scope():
    """
    Validate that URL scope matches JWT scope for API routes.

    Should be registered as before_request handler.

    Returns:
        Error response if validation fails, None otherwise
    """
    # Only validate scoped API routes
    if "/api/" not in request.path:
        return None

    # Exempt auth endpoints
    if "/api/auth/login" in request.path or "/api/auth/logout" in request.path:
        return None

    # Extract scope from URL
    url_scope = extract_scope_from_path(request.path)
    if url_scope is None:
        # Legacy /api/* route, skip validation
        return None

    user = get_current_user()

    # Validate employee is logged in
    if not user:
        logger.warning(f"JWT Scope Guard - No token for {request.path}")
        return jsonify(
            {
                "error": "Authentication required",
                "code": "AUTH_REQUIRED",
                "hint": "Please login first",
            }
        ), 401

    # Validate scope match
    jwt_scope = user.get("active_scope")
    if not jwt_scope:
        logger.warning(f"JWT Scope Guard - No scope in token for {request.path}")
        return jsonify(
            {
                "error": "No active session scope",
                "code": "SCOPE_MISSING",
                "hint": "Please login first",
            }
        ), 401

    if jwt_scope != url_scope:
        logger.warning(
            f"JWT Scope Guard - Mismatch: URL={url_scope}, token={jwt_scope}, "
            f"path={request.path}, employee={user.get('employee_id')}"
        )
        return jsonify(
            {
                "error": f"Scope mismatch: URL requires {url_scope}, but token is {jwt_scope}",
                "code": "SCOPE_MISMATCH",
                "hint": f"This endpoint requires {url_scope} access.",
            }
        ), 403

    return None


def extract_scope_from_path(path: str) -> str | None:
    """Extract scope from URL path."""
    parts = path.lstrip("/").split("/")
    if len(parts) >= 1:
        scope = parts[0]
        if scope in ["waiter", "chef", "cashier", "admin", "system"]:
            return scope
    return None


def apply_jwt_scope_guard(app: Flask) -> None:
    """
    Apply JWT-based scope validation to all /<scope>/api/* routes.

    Args:
        app: Flask application instance
    """

    @app.before_request
    def jwt_scope_guard():
        return validate_api_scope()
