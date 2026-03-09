# ruff: noqa: E402
"""
Tests for client payments API endpoints.

These tests verify the BFF proxy behavior for payment endpoints.
All tests use PRONTO_ROUTES_ONLY=1 to avoid DB dependencies.
"""

import os
import sys
import types
import uuid
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
# PAY SESSION
# =============================================================================

def test_pay_session_forwards_to_api():
    """Pay session endpoint should forward request to pronto-api."""
    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "success", "data": {"payment_id": "pay_123", "amount": 500.00}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/sessions/{session_id}/pay",
            json={"amount": 500.00, "method": "card"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


def test_pay_session_with_tip_forwards_to_api():
    """Pay session with tip should forward correctly."""
    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "success", "data": {"payment_id": "pay_456", "total": 575.00}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/sessions/{session_id}/pay",
            json={"amount": 500.00, "tip": 75.00, "method": "card"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# PAY CASH
# =============================================================================

def test_pay_cash_forwards_to_api():
    """Pay cash endpoint should forward request to pronto-api."""
    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "success", "data": {"payment_id": "cash_123", "amount": 500.00}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/sessions/{session_id}/pay/cash",
            json={"amount": 500.00},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


def test_pay_cash_with_cash_received_forwards_to_api():
    """Pay cash with cash_received should forward correctly."""
    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "payment_id": "cash_456",
                "amount": 500.00,
                "cash_received": 600.00,
                "change": 100.00
            }
        },
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/sessions/{session_id}/pay/cash",
            json={"amount": 500.00, "cash_received": 600.00},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# PAYMENT METHODS
# =============================================================================

def test_get_payment_methods_forwards_to_api():
    """Get payment methods should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "methods": [
                    {"id": "cash", "name": "Efectivo", "enabled": True},
                    {"id": "card", "name": "Tarjeta", "enabled": True},
                    {"id": "stripe", "name": "Stripe", "enabled": False}
                ]
            }
        },
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get("/api/methods")

    assert response.status_code == 200


# =============================================================================
# Error Handling
# =============================================================================

def test_pay_session_handles_api_timeout():
    """Pay session should handle timeout gracefully."""
    import requests

    client = _client_app()
    session_id = uuid.uuid4()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.Timeout()):
        response = client.post(
            f"/api/sessions/{session_id}/pay",
            json={"amount": 500.00},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 504  # GATEWAY_TIMEOUT


def test_pay_session_handles_api_error():
    """Pay session should handle API errors gracefully."""
    import requests

    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "error", "message": "Insufficient funds"},
        status_code=400
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/sessions/{session_id}/pay",
            json={"amount": 500.00},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 400


def test_pay_session_handles_connection_error():
    """Pay session should handle connection errors gracefully."""
    import requests

    client = _client_app()
    session_id = uuid.uuid4()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.RequestException()):
        response = client.post(
            f"/api/sessions/{session_id}/pay",
            json={"amount": 500.00},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 502  # BAD_GATEWAY
