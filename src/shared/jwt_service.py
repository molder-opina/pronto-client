"""
JWT Service - Token generation and validation for Pronto.

Replaces filesystem/Redis session management with stateless JWT tokens.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from flask import Request, current_app

# JWT configuration
def get_access_token_expiry() -> int:
    try:
        return current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 24)
    except RuntimeError:
        return int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "24"))

def get_refresh_token_expiry() -> int:
    try:
        return current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 7)
    except RuntimeError:
        return int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))

JWT_ALGORITHM = "HS256"


class JWTError(Exception):
    """Base exception for JWT errors."""

    def __init__(self, message: str, status: int = 401):
        self.message = message
        self.status = status
        super().__init__(message)


class TokenExpiredError(JWTError):
    """Token has expired."""

    def __init__(self):
        super().__init__("Token expired", 401)


class InvalidTokenError(JWTError):
    """Token is invalid or malformed."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, 401)


def get_jwt_secret() -> str:
    """Get JWT secret key from config or environment."""
    # Try Flask app config first
    try:
        secret = current_app.config.get("SECRET_KEY")
        if secret:
            return secret
    except RuntimeError:
        pass

    # Fall back to environment variable
    secret = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET_KEY"))
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY or SECRET_KEY must be configured")
    return secret


def create_access_token(
    employee_id: int,
    employee_name: str,
    employee_email: str,
    employee_role: str,
    employee_additional_roles: list[str] | None = None,
    active_scope: str | None = None,
    expires_hours: int | None = None,
) -> str:
    """
    Create a JWT access token for an employee.

    Args:
        employee_id: Employee database ID
        employee_name: Employee display name
        employee_email: Employee email
        employee_role: Primary role (waiter, chef, cashier, admin)
        employee_additional_roles: Additional roles list
        active_scope: Current active scope (waiter, chef, cashier, admin)
        expires_hours: Token expiration in hours (default: 24)

    Returns:
        Encoded JWT token string
    """
    secret = get_jwt_secret()
    expires = expires_hours or get_access_token_expiry()

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(employee_id),
        "iat": now,
        "exp": now + timedelta(hours=expires),
        "type": "access",
        # Employee data
        "employee_id": employee_id,
        "employee_name": employee_name,
        "employee_email": employee_email,
        "employee_role": employee_role,
        "employee_additional_roles": employee_additional_roles,
        "active_scope": active_scope,
    }

    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(employee_id: int, expires_days: int | None = None) -> str:
    """
    Create a JWT refresh token for an employee.

    Args:
        employee_id: Employee database ID
        expires_days: Token expiration in days (default: 7)

    Returns:
        Encoded JWT refresh token string
    """
    secret = get_jwt_secret()
    expires = expires_days or get_refresh_token_expiry()

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(employee_id),
        "iat": now,
        "exp": now + timedelta(days=expires),
        "type": "refresh",
        "employee_id": employee_id,
    }

    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, verify_type: str | None = None) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string
        verify_type: Expected token type ('access' or 'refresh')

    Returns:
        Decoded token payload

    Raises:
        TokenExpiredError: If token has expired
        InvalidTokenError: If token is invalid
    """
    secret = get_jwt_secret()

    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])

        # Verify token type if specified
        if verify_type and payload.get("type") != verify_type:
            raise InvalidTokenError(f"Expected {verify_type} token")

        return payload

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(str(e))


def extract_token_from_request(request: Request) -> str | None:
    """
    Extract JWT token from request.

    Checks in order:
    1. Authorization header (Bearer token)
    2. X-Access-Token header
    3. access_token cookie

    Args:
        request: Flask request object

    Returns:
        Token string if found, None otherwise
    """
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    # Check X-Access-Token header
    token_header = request.headers.get("X-Access-Token")
    if token_header:
        return token_header

    # Check cookie
    return request.cookies.get("access_token")


def get_current_user(request: Request) -> dict[str, Any] | None:
    """
    Get current authenticated user from request.

    Args:
        request: Flask request object

    Returns:
        User payload dict if authenticated, None otherwise
    """
    token = extract_token_from_request(request)
    if not token:
        return None

    try:
        return decode_token(token, verify_type="access")
    except JWTError:
        return None


def create_client_token(
    customer_id: int | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    table_id: int | None = None,
    session_id: int | None = None,
    expires_hours: int = 4,
) -> str:
    """
    Create a JWT token for client/customer sessions.

    Args:
        customer_id: Customer database ID (optional for guests)
        customer_name: Customer name
        customer_phone: Customer phone
        table_id: Current table ID
        session_id: Current dining session ID
        expires_hours: Token expiration in hours

    Returns:
        Encoded JWT token string
    """
    secret = get_jwt_secret()

    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
        "type": "client",
        # Customer data
        "customer_id": customer_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "table_id": table_id,
        "session_id": session_id,
    }

    if customer_id:
        payload["sub"] = str(customer_id)

    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
