"""
Scope Guard Middleware - JWT-based multi-layer scope validation.

Layer 1: ScopeGuard class (dashboard access control)
Layer 2: API scope validation (URL-based perimeter)
"""

import logging
from functools import wraps
from typing import Optional

from flask import flash, jsonify, make_response, redirect, request, url_for

from shared.jwt_middleware import get_active_scope, get_current_user

logger = logging.getLogger(__name__)


class ScopeGuard:
    def __init__(self, app_scope, login_route):
        """
        Initialize the guard with the required scope and login route
        to redirect to if unauthorized.

        Args:
            app_scope (str): The scope required for this app (e.g. 'waiter', 'chef')
            login_route (str): The login endpoint to redirect to (e.g. 'waiter_app.login')
        """
        self.app_scope = app_scope
        self.login_route = login_route

    def __call__(self):
        """
        This middleware is executed before_request in each Blueprint.
        It enforces multi-scope isolation by checking JWT token:
        1. User is logged in (has employee_id in JWT)
        2. User's active_scope matches required app_scope
        """
        logger.info(
            f"ScopeGuard({self.app_scope}) - Processing {request.method} {request.path} - Endpoint: {request.endpoint}"
        )

        # 1. Ignore public endpoints (login, static) within the blueprint
        if request.endpoint and (
            request.endpoint.endswith(".login")
            or request.endpoint.endswith(".process_login")
            or "static" in request.endpoint
        ):
            logger.info(f"ScopeGuard({self.app_scope}) - Public endpoint, bypassing guard")
            return None

        # 2. Check if guard already handled this request
        if request.view_args and request.view_args.get("_guard_handled"):
            logger.info(
                f"ScopeGuard({self.app_scope}) - Guard already handled request, skipping route handler"
            )
            return None

        # 3. Check for JWT authentication
        user = get_current_user()
        if not user or not user.get("employee_id"):
            logger.warning(
                f"ScopeGuard({self.app_scope}) - No employee_id in JWT, redirecting to login"
            )
            response = redirect(url_for(self.login_route, next=request.url))
            response.headers["_guard_handled"] = "true"
            return response

        # 4. CRITICAL CONTEXT VERIFICATION
        # The JWT must have the correct scope
        current_scope = user.get("active_scope")

        logger.info(
            f"ScopeGuard({self.app_scope}) - current_scope={current_scope}, required={self.app_scope}"
        )

        if current_scope != self.app_scope:
            scope_names = {
                "waiter": "Mesero",
                "chef": "Chef/Cocina",
                "cashier": "Caja",
                "admin": "Administración",
                "system": "Sistema",
            }
            current_scope_val = current_scope or "sin acceso"
            current_scope_name = scope_names.get(current_scope_val, current_scope_val)
            required_scope_name = scope_names.get(self.app_scope, self.app_scope)

            logger.warning(
                f"ScopeGuard({self.app_scope}) - Scope mismatch: {current_scope} != {self.app_scope}, redirecting to login"
            )
            flash(
                f"No tiene permisos para acceder a esta sección. "
                f"Su rol actual es: {current_scope_name}. "
                f"Por favor inicie sesión como {required_scope_name}.",
                "error",
            )
            response = redirect(url_for(self.login_route))
            response.headers["_guard_handled"] = "true"
            return response

        logger.info(
            f"ScopeGuard({self.app_scope}) - Request passed guard checks, allowing route handler to proceed"
        )
        return None


# ============================================================================
# API SCOPE VALIDATION (URL-based perimeter)
# ============================================================================


def extract_scope_from_path(path: str) -> str | None:
    """
    Extract scope from URL path.

    Examples:
        /waiter/api/orders -> "waiter"
        /chef/api/orders -> "chef"
        /api/orders -> None (legacy, no scope)

    Returns:
        Scope name if found, None otherwise
    """
    parts = path.lstrip("/").split("/")
    if len(parts) >= 2 and parts[1] == "api":
        # Pattern: /<scope>/api/*
        scope = parts[0]
        if scope in ["waiter", "chef", "cashier", "admin", "system"]:
            return scope
    return None


def require_scope_match(f):
    """
    Decorator that validates scope consistency for API routes.

    Validates that:
    1. URL scope matches JWT active_scope
    2. Prevents scope confusion attacks

    Usage:
        @waiter_api_bp.route('/api/orders')
        @require_scope_match
        def list_orders():
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract scope from URL
        url_scope = extract_scope_from_path(request.path)

        # If no scope in URL, allow (legacy /api/* routes)
        if url_scope is None:
            return f(*args, **kwargs)

        # Get JWT scope
        jwt_scope = get_active_scope()

        # Validate match
        if not jwt_scope:
            logger.warning(f"API Scope Guard - No JWT scope for {request.path}")
            return jsonify(
                {
                    "error": "No active session scope",
                    "code": "SCOPE_MISSING",
                    "hint": "Please login first",
                }
            ), 401

        if jwt_scope != url_scope:
            logger.warning(
                f"API Scope Guard - Mismatch: URL={url_scope}, JWT={jwt_scope}, path={request.path}"
            )
            scope_names = {
                "waiter": "Mesero",
                "chef": "Chef/Cocina",
                "cashier": "Caja",
                "admin": "Administración",
                "system": "Sistema",
            }
            url_scope_name = scope_names.get(url_scope, url_scope)
            jwt_scope_name = scope_names.get(jwt_scope or "sin acceso", jwt_scope or "sin acceso")
            return jsonify(
                {
                    "error": f"Acceso denegado: Necesitas permisos de {url_scope_name}",
                    "code": "SCOPE_MISMATCH",
                    "hint": f"Tu cuenta tiene permisos de {jwt_scope_name}. Esta sección requiere acceso de {url_scope_name}.",
                }
            ), 403

        # Scope is valid, proceed
        logger.debug(f"API Scope Guard - Valid: {url_scope} for {request.path}")
        return f(*args, **kwargs)

    return decorated_function


def apply_api_scope_guard(app):
    """
    Apply global API scope validation to all /<scope>/api/* routes.

    This middleware runs before_request and validates that the URL scope
    matches the JWT scope, preventing scope confusion attacks.

    NOTE: This is now a pass-through as JWT middleware handles this.
    Kept for backward compatibility with existing code.

    Usage (in app.py):
        from shared.scope_guard import apply_api_scope_guard
        apply_api_scope_guard(app)
    """
    # JWT middleware in jwt_middleware.py now handles scope validation
    # This function is kept for backward compatibility
    pass
