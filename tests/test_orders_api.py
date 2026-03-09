# ruff: noqa: E402
"""
Tests for client orders API endpoints.

These tests verify the BFF proxy behavior for order endpoints.
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
# GET CUSTOMER ORDERS (History)
# =============================================================================

def test_get_customer_orders_forwards_to_api():
    """Get customer orders should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "orders": [
                    {"id": "order_1", "total": 250.00, "status": "completed"},
                    {"id": "order_2", "total": 180.00, "status": "completed"}
                ]
            }
        },
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get("/api/customer/orders")

    assert response.status_code == 200


# =============================================================================
# CREATE CUSTOMER ORDER
# =============================================================================

def test_create_customer_order_forwards_to_api():
    """Create customer order should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "order_id": "order_123",
                "items": [{"product_id": "prod_1", "quantity": 2}]
            }
        },
        status_code=201
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/customer/orders",
            json={"items": [{"product_id": "prod_1", "quantity": 2}]},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 201


# =============================================================================
# REQUEST CHECK
# =============================================================================

def test_request_customer_check_forwards_to_api():
    """Request customer check should forward request to pronto-api."""
    client = _client_app()
    session_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "success", "data": {"check_requested": True}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/customer/orders/session/{session_id}/request-check",
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# CREATE ORDER
# =============================================================================

def test_create_order_forwards_to_api():
    """Create order should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "order_id": "order_456",
                "session_id": str(uuid.uuid4()),
                "items": []
            }
        },
        status_code=201
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/orders",
            json={"session_id": str(uuid.uuid4())},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 201


# =============================================================================
# GET ORDER
# =============================================================================

def test_get_order_forwards_to_api():
    """Get order details should forward request to pronto-api."""
    client = _client_app()
    order_id = uuid.uuid4()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "id": str(order_id),
                "items": [
                    {"product_name": "Taco", "quantity": 3, "price": 25.00}
                ],
                "total": 75.00,
                "status": "pending"
            }
        },
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get(f"/api/orders/{order_id}")

    assert response.status_code == 200


def test_get_order_not_found():
    """Get order should return 404 for non-existent order."""
    client = _client_app()
    order_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "error", "message": "Order not found"},
        status_code=404
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get(f"/api/orders/{order_id}")

    assert response.status_code == 404


# =============================================================================
# ADD ORDER ITEM
# =============================================================================

def test_add_order_item_forwards_to_api():
    """Add order item should forward request to pronto-api."""
    client = _client_app()
    order_id = uuid.uuid4()

    mock_response = MockResponse(
        {
            "status": "success",
            "data": {
                "item_id": "item_123",
                "product_id": "prod_1",
                "quantity": 2,
                "price": 50.00
            }
        },
        status_code=201
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            f"/api/orders/{order_id}/items",
            json={"product_id": "prod_1", "quantity": 2},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 201


# =============================================================================
# DELETE ORDER ITEM
# =============================================================================

def test_delete_order_item_forwards_to_api():
    """Delete order item should forward request to pronto-api."""
    client = _client_app()
    order_id = uuid.uuid4()
    item_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "success", "data": {"deleted": True}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.delete", return_value=mock_response):
        response = client.delete(f"/api/orders/{order_id}/items/{item_id}")

    assert response.status_code == 200


def test_delete_order_item_not_found():
    """Delete order item should return 404 for non-existent item."""
    client = _client_app()
    order_id = uuid.uuid4()
    item_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "error", "message": "Item not found"},
        status_code=404
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.delete", return_value=mock_response):
        response = client.delete(f"/api/orders/{order_id}/items/{item_id}")

    assert response.status_code == 404


# =============================================================================
# SEND ORDER CONFIRMATION
# =============================================================================

def test_send_order_confirmation_forwards_to_api():
    """Send order confirmation should forward request to pronto-api."""
    client = _client_app()

    mock_response = MockResponse(
        {"status": "success", "data": {"email_sent": True}},
        status_code=200
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.post", return_value=mock_response):
        response = client.post(
            "/api/orders/send-confirmation",
            json={"order_id": str(uuid.uuid4()), "email": "customer@test.com"},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 200


# =============================================================================
# Error Handling
# =============================================================================

def test_create_order_handles_api_timeout():
    """Create order should handle timeout gracefully."""
    import requests

    client = _client_app()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.Timeout()):
        response = client.post(
            "/api/orders",
            json={"session_id": str(uuid.uuid4())},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 504  # GATEWAY_TIMEOUT


def test_create_order_handles_connection_error():
    """Create order should handle connection errors gracefully."""
    import requests

    client = _client_app()

    with patch("pronto_clients.routes.api._upstream.http_requests.post", side_effect=requests.RequestException()):
        response = client.post(
            "/api/orders",
            json={"session_id": str(uuid.uuid4())},
            headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 502  # BAD_GATEWAY


def test_get_order_handles_api_error():
    """Get order should handle API errors gracefully."""
    client = _client_app()
    order_id = uuid.uuid4()

    mock_response = MockResponse(
        {"status": "error", "message": "Unauthorized"},
        status_code=401
    )

    with patch("pronto_clients.routes.api._upstream.http_requests.get", return_value=mock_response):
        response = client.get(f"/api/orders/{order_id}")

    assert response.status_code == 401
