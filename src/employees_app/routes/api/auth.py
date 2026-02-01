"""
Auth API - JWT-based authentication endpoints.

Handles employee login, logout, token refresh, and current user info.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, make_response, request
from pydantic import ValidationError as PydanticValidationError


from shared.auth.service import AuthError, AuthService
from shared.jwt_middleware import extract_scope_from_path, get_current_user, get_employee_id, jwt_required
from shared.jwt_service import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_token_from_request,
)
from shared.logging_config import get_logger
from shared.permissions import get_user_permissions
from shared.schemas import LoginRequest
from shared.security_middleware import rate_limit
from shared.serializers import error_response, success_response

# Create blueprint without url_prefix (inherited from parent)
auth_bp = Blueprint("auth", __name__)
logger = get_logger(__name__)


# Removed local _extract_scope_from_path, using shared extraction.


@auth_bp.post("/auth/login")
@rate_limit(max_requests=5, window_seconds=60)
def post_login():
    """
    Authenticate employee and issue JWT tokens.

    Body:
        {
            "email": str,
            "password": str
        }

    Returns:
        {
            "success": true,
            "access_token": str,
            "refresh_token": str,
            "employee": {...}
        }

    Rate limit: 5 attempts per minute
    """
    payload = request.get_json(silent=True) or {}

    try:
        login_data = LoginRequest(**payload)
    except PydanticValidationError as e:
        logger.warning(f"Login validation error: {e}")
        return jsonify(
            error_response("Datos de login invalidos", {"details": e.errors()})
        ), HTTPStatus.BAD_REQUEST

    try:
        auth_result = AuthService.authenticate(login_data.email, login_data.password)
        employee = auth_result.employee

        # Determine scope from URL path
        active_scope = extract_scope_from_path(request.path)

        # If no scope in URL (shared endpoint), fallback to role-based scope
        if not active_scope:
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

        logger.info(f"Employee {employee.id} ({employee.email}) logged in via JWT")

        # Create response with tokens
        response_data = success_response(
            {
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "employee": {
                    "id": employee.id,
                    "name": employee.name,
                    "email": employee.email,
                    "role": employee.role,
                    "additional_roles": employee.additional_roles,
                },
            }
        )

        response = make_response(jsonify(response_data))

        # Also set token as HTTP-only cookie for web app convenience
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            max_age=86400,  # 24 hours
            path="/",
        )
        response.set_cookie(
            "refresh_token",
            refresh_token,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            max_age=604800,  # 7 days
            path="/",
        )

        return response

    except AuthError as exc:
        logger.warning(f"Failed login attempt for {login_data.email}: {exc}")
        return jsonify(error_response(str(exc))), exc.status


@auth_bp.post("/auth/logout")
def post_logout():
    """
    Logout - clears JWT cookies.

    For stateless JWT, the token isn't invalidated server-side.
    Client should discard the token.
    """
    response = make_response(jsonify({"success": True}))

    # Clear cookies
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")

    return response


@auth_bp.post("/auth/refresh")
@rate_limit(max_requests=10, window_seconds=60)
def post_refresh():
    """
    Refresh access token using refresh token.

    Body (optional if using cookie):
        {
            "refresh_token": str
        }

    Returns:
        {
            "success": true,
            "access_token": str
        }
    """
    # Get refresh token from body or cookie
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or request.cookies.get("refresh_token")

    if not refresh_token:
        return jsonify(error_response("Refresh token required")), HTTPStatus.BAD_REQUEST

    try:
        # Validate refresh token
        token_data = decode_token(refresh_token, verify_type="refresh")
        employee_id = token_data.get("employee_id")

        if not employee_id:
            return jsonify(error_response("Invalid refresh token")), HTTPStatus.UNAUTHORIZED

        # Fetch current employee data from DB
        from shared.db import get_session
        from shared.models import Employee

        with get_session() as db_session:
            employee = db_session.query(Employee).filter_by(id=employee_id).first()
            if not employee:
                return jsonify(error_response("Employee not found")), HTTPStatus.UNAUTHORIZED
            if not employee.is_active:
                return jsonify(error_response("Account is inactive")), HTTPStatus.UNAUTHORIZED

            # Determine scope from current request
            active_scope = extract_scope_from_path(request.path)

            # If no scope in URL (shared endpoint), fallback to role-based scope
            if not active_scope:
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

            # Create new access token
            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=employee.email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope=active_scope,
            )

        response_data = success_response(
            {
                "success": True,
                "access_token": access_token,
            }
        )

        response = make_response(jsonify(response_data))

        # Update access token cookie
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            max_age=86400,
            path="/",
        )

        return response

    except TokenExpiredError:
        logger.info("Refresh token expired")
        return jsonify(error_response("Refresh token expired")), HTTPStatus.UNAUTHORIZED
    except InvalidTokenError as e:
        logger.warning(f"Invalid refresh token: {e}")
        return jsonify(error_response("Invalid refresh token")), HTTPStatus.UNAUTHORIZED


@auth_bp.get("/auth/me")
@jwt_required
def get_current_employee():
    """
    Get current authenticated employee info from JWT.

    Returns employee data from the JWT payload.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), HTTPStatus.UNAUTHORIZED

    return jsonify(
        {
            "employee": {
                "id": user.get("employee_id"),
                "name": user.get("employee_name"),
                "email": user.get("employee_email"),
                "role": user.get("employee_role"),
                "additional_roles": user.get("employee_additional_roles"),
            }
        }
    )


@auth_bp.get("/auth/permissions")
@jwt_required
def get_permissions():
    """
    Get permissions for the authenticated employee.

    Returns role-based permissions and capabilities.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), HTTPStatus.UNAUTHORIZED

    role = user.get("employee_role")
    if not role:
        return jsonify({"error": "No role found in token"}), HTTPStatus.UNAUTHORIZED

    permissions_info = get_user_permissions(role)

    return jsonify(permissions_info)


@auth_bp.get("/auth/verify")
def verify_token():
    """
    Verify if the current token is valid.

    Returns token status and user info if valid.
    """
    token = extract_token_from_request(request)
    if not token:
        return jsonify({"valid": False, "error": "No token provided"}), HTTPStatus.OK

    try:
        payload = decode_token(token, verify_type="access")
        return jsonify(
            {
                "valid": True,
                "employee_id": payload.get("employee_id"),
                "employee_role": payload.get("employee_role"),
                "active_scope": payload.get("active_scope"),
            }
        )
    except TokenExpiredError:
        return jsonify({"valid": False, "error": "Token expired"}), HTTPStatus.OK
    except InvalidTokenError as e:
        return jsonify({"valid": False, "error": str(e)}), HTTPStatus.OK
