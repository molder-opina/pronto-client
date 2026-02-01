"""
Security middleware for XSS protection, rate limiting, and session security.
"""

import html
import os
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

from flask import current_app, jsonify, request


def get_client_ip() -> str:
    """
    Get real client IP considering proxies (Docker, nginx, etc.).

    Returns:
        Client IP address string
    """
    # Check for common proxy headers (in order of preference)
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        # X-Forwarded-For: client, proxy1, proxy2
        # Take the first (original client) IP
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()

    return request.remote_addr or "unknown"


class RateLimiter:
    """Simple in-memory rate limiter with IP awareness."""

    def __init__(self):
        self.requests: dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if request is allowed based on rate limit.

        Args:
            key: Unique identifier (e.g., IP address + endpoint)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = time.time()
        cutoff = now - window_seconds

        # Clean old entries
        self.requests[key] = [t for t in self.requests[key] if t > cutoff]

        remaining = max_requests - len(self.requests[key])

        if len(self.requests[key]) >= max_requests:
            return False, 0

        self.requests[key].append(now)
        return True, remaining - 1

    def clean_old_entries(self, max_age_seconds: int = 3600):
        """Remove entries older than max_age to prevent memory leak."""
        now = time.time()
        cutoff = now - max_age_seconds

        for key in list(self.requests.keys()):
            self.requests[key] = [t for t in self.requests[key] if t > cutoff]
            if not self.requests[key]:
                del self.requests[key]


_rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 5, window_seconds: int = 60, key_prefix: str = ""):
    """
    Decorator to rate limit endpoints.

    Args:
        max_requests: Maximum requests allowed per window
        window_seconds: Time window in seconds
        key_prefix: Optional prefix for the rate limit key

    Returns:
        Decorated function that enforces rate limiting
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            testing_mode = False
            if current_app:
                testing_mode = bool(current_app.config.get("TESTING"))
            if not testing_mode:
                testing_mode = os.getenv("TESTING", "").lower() in {"1", "true", "yes", "on"}

            if testing_mode:
                return f(*args, **kwargs)

            # Get client IP considering proxies
            client_ip = get_client_ip()

            # Create unique key: IP + endpoint path (to allow different limits per endpoint)
            endpoint_key = f"{key_prefix}{request.path}"

            key = f"{client_ip}:{endpoint_key}"

            is_allowed, remaining = _rate_limiter.is_allowed(key, max_requests, window_seconds)

            if not is_allowed:
                response = jsonify(
                    {
                        "error": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
                        "retry_after": window_seconds,
                        "data": None,
                    }
                )
                response.status_code = HTTPStatus.TOO_MANY_REQUESTS
                # Add rate limit headers
                response.headers["Retry-After"] = str(window_seconds)
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = "0"
                return response

            response = f(*args, **kwargs)

            # Add rate limit headers to successful responses
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = str(remaining)

            return response

        return decorated_function

    return decorator


def sanitize_input(value: Any) -> Any:
    """
    Sanitize input to prevent XSS attacks.

    Args:
        value: Input value (can be str, dict, list, or other)

    Returns:
        Sanitized value
    """
    if isinstance(value, str):
        return html.escape(value)
    elif isinstance(value, dict):
        return {k: sanitize_input(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_input(item) for item in value]
    else:
        return value


def sanitize_request_data():
    """
    Sanitize all incoming request data (JSON, form, args).

    Call this in before_request handler.
    """
    if request.is_json:
        request._cached_json = sanitize_input(request.get_json(silent=True))

    if request.form:
        request._cached_form = sanitize_input(dict(request.form))

    if request.args:
        request._cached_args = sanitize_input(dict(request.args))


def _extract_origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def configure_security_headers(app):
    """
    Configure security headers for Flask app.

    Args:
        app: Flask application instance
    """
    static_origin = _extract_origin(app.config.get("PRONTO_STATIC_CONTAINER_HOST"))
    app.config.get("ENV") == "development" or app.config.get("DEBUG_MODE", False)

    # Base sources (allow schemes to prevent CSP blocks with CDN/static assets)
    script_sources = ["'self'", "'unsafe-inline'", "'unsafe-eval'", "https:", "http:"]
    style_sources = ["'self'", "'unsafe-inline'", "https:", "http:", "https://fonts.googleapis.com"]
    connect_sources = ["'self'", "https:", "http:"]
    img_sources = ["'self'", "data:", "https:", "http:"]
    font_sources = ["'self'", "data:", "https:", "http:", "https://fonts.gstatic.com"]

    # CDN sources for scripts/styles
    cdn_script_sources = [
        "https://cdn.socket.io",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
    ]
    script_sources.extend(cdn_script_sources)
    style_sources.extend(["https://fonts.googleapis.com"])
    font_sources.extend(["https://fonts.gstatic.com"])

    # WebSocket connections
    connect_sources.extend(
        ["wss://pronto-admin.molderx.xyz", "wss://pronto-app.molderx.xyz", "https://cdn.socket.io"]
    )

    # Static origin (if configured)
    if static_origin:
        script_sources.append(static_origin)
        style_sources.append(static_origin)
        connect_sources.append(static_origin)
        img_sources.append(static_origin)

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        request_path = request.path

        # Cache headers for static assets (1 year - immutable)
        if (
            request_path.startswith("/static/")
            or "/dist/" in request_path
            or "/assets/" in request_path
            or any(
                s in request_path
                for s in [".js", ".css", ".woff2", ".png", ".jpg", ".jpeg", ".svg", ".ico"]
            )
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Vary"] = "Accept-Encoding"

        # Cache headers for immutable API responses (1 minute)
        elif request.method == "GET" and "/api/" in request_path:
            response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=30"

        # Disable caching for HTML pages (force browser to reload)
        elif response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        csp_directives = [
            "default-src 'self'",
            f"connect-src {' '.join(connect_sources)}",
            f"script-src {' '.join(script_sources)}",
            f"style-src {' '.join(style_sources)}",
            f"font-src {' '.join(font_sources)}",
            f"img-src {' '.join(img_sources)}",
            "media-src 'self' data: https:",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives) + ";"

        return response


def configure_session_security(app):
    """
    Configure secure session settings.

    Args:
        app: Flask application instance
    """
    # Respect explicit SESSION_COOKIE_SECURE configurations coming from the app/env.
    secure_cookie = app.config.get("SESSION_COOKIE_SECURE")
    if isinstance(secure_cookie, str):
        secure_cookie = secure_cookie.strip().lower() in {"1", "true", "yes", "on"}

    if secure_cookie is None:
        # Default to secure cookies unless running in debug mode.
        secure_cookie = not app.config.get("DEBUG_MODE", False)

    app.config["SESSION_COOKIE_SECURE"] = bool(secure_cookie)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", 3600 * 8)  # 8 hours
