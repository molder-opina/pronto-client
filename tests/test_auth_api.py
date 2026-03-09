# ruff: noqa: E402
"""
Tests for client authentication API endpoints.

These tests verify the BFF proxy behavior for auth endpoints.
All tests use PRONTO_ROUTES_ONLY=1 to avoid DB dependencies.
"""

import os
import sys
import types
from unittest.mock import patch, MagicMock

os.environ.setdefault("PRONTO_ROUTES_ONLY", "1")

if "flask_wtf.csrf" not in sys.modules:
    flask_wtf_module = types.ModuleType("flask_wtf")
    csrf_module = types.ModuleType("flask_wtf.csrf")

    class _CSRFProtect:
        def init_app(self, _app):
            return None

        def protect(self):
            return None

        def exempt(self, func):
            return func

    csrf_module.CSRFProtect = _CSRFProtect
    csrf_module.generate_csrf = lambda: "test-csrf-token"
    flask_wtf_module.csrf = csrf_module
    sys.modules["flask_wtf"] = flask_wtf_module
    sys.modules["flask_wtf.csrf"] = csrf_module

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pronto-client" / "src"))
sys.path.insert(0, str(ROOT / "pronto-libs" / "src"))

from pronto_clients.app import create_app


def _client_app():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


class MockResponse:
    """Mock HTTP response for requests library."""
    def __init__(self, json_data, status_code=200, headers=None):
        self._json = json_data
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}
        self.raw = MagicMock()
        self.raw.headers = headers or {}
        self.content = b""

    def json(self):
        return self._json


# =============================================================================
# LOGIN
# =============================================================================

def test_login_forwards_to_api():
    """Login endpoint should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success", "data": {"customer_id": "123", "name": "Juan"}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/client-auth/login",
            json={"email": "juan@test.com", "password": "secret"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


def test_login_returns_error_on_api_failure():
    """Login should return error when API fails."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "error", "message": "Invalid credentials"},
        status_code=401
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/client-auth/login",
            json={"email": "wrong@test.com", "password": "wrong"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 401


# =============================================================================
# REGISTER
# =============================================================================

def test_register_forwards_to_api():
    """Register endpoint should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success", "data": {"customer_id": "456", "name": "María"}},
        status_code=201
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/client-auth/register",
            json={"email": "maria@test.com", "password": "secret", "first_name": "María"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 201


# =============================================================================
# LOGOUT
# =============================================================================

def test_logout_forwards_to_api():
    """Logout endpoint should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success"},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/client-auth/logout",
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# ME (Profile)
# =============================================================================

def test_me_forwards_to_api():
    """Me endpoint should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success", "data": {"customer_id": "123", "name": "Juan", "email": "juan@test.com"}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get(
            "/api/client-auth/me",
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


def test_update_me_forwards_to_api():
    """Update me endpoint should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success", "data": {"customer_id": "123", "name": "Juan Updated"}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.put", return_value=mock_response):
        response = client.put(
            "/api/client-auth/me",
            json={"first_name": "Juan Updated"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# CSRF Token
# =============================================================================

def test_csrf_endpoint_returns_token():
    """CSRF endpoint should return a fresh token."""
    client = _client_app()

    response = client.get("/api/client-auth/csrf")

    assert response.status_code == 200
    data = response.get_json()
    assert "data" in data
    assert "csrf_token" in data["data"]


# =============================================================================
# Error Handling
# =============================================================================

def test_login_handles_api_timeout():
    """Login should handle timeout gracefully."""
    import requests

    client = _client_app()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.Timeout()):
        response = client.post(
            "/api/client-auth/login",
            json={"email": "test@test.com", "password": "secret"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 504  # GATEWAY_TIMEOUT


def test_login_handles_api_connection_error():
    """Login should handle connection errors gracefully."""
    import requests

    client = _client_app()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.RequestException()):
        response = client.post(
            "/api/client-auth/login",
            json={"email": "test@test.com", "password": "secret"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 502  # BAD_GATEWAY
