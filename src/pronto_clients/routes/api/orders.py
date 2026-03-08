"""
Orders endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: pronto-api no tiene endpoints completos de gestión de órdenes para clientes.
      Solo tiene /modifications para aprobar/rechazar modificaciones.
      Esta es una limitación temporal.
"""

from __future__ import annotations

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, Response, request

from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

orders_bp = Blueprint("client_orders", __name__)


def _forward_to_api(method: str, path: str, data: dict | None = None):
    """
    Forward request to pronto-api.
    
    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    No business logic is applied here.
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    
    headers = {
        "X-PRONTO-CUSTOMER-REF": request.headers.get("X-PRONTO-CUSTOMER-REF", ""),
        "Content-Type": "application/json",
    }
    
    # Forward correlation ID if present
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    csrf_token = request.headers.get("X-CSRFToken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    
    try:
        if method == "GET":
            response = http_requests.get(
                url,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        elif method == "POST":
            response = http_requests.post(
                url,
                json=data,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        elif method == "DELETE":
            response = http_requests.delete(
                url,
                headers=headers,
                cookies=request.cookies,
                timeout=5,
                allow_redirects=False,
                stream=True,
            )
        else:
            from pronto_shared.serializers import error_response
            return error_response("Method not supported"), HTTPStatus.METHOD_NOT_ALLOWED

        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = [
            (k, v)
            for k, v in response.raw.headers.items()
            if k.lower() not in excluded_headers
        ]

        return Response(
            response.content,
            status=response.status_code,
            headers=response_headers,
            content_type=response.headers.get("Content-Type"),
        )
    
    except http_requests.Timeout:
        from pronto_shared.serializers import error_response
        return error_response("Timeout conectando a API"), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        from pronto_shared.serializers import error_response
        return error_response("Error conectando a API"), HTTPStatus.BAD_GATEWAY


@orders_bp.get("/customer/orders")
def get_customer_orders():
    """PROXY: Get orders for customer (historial)."""
    path = "/api/customer/orders"
    return _forward_to_api("GET", path)


@orders_bp.post("/customer/orders")
def create_customer_order():
    """PROXY: Create customer order (session-scoped client flow)."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customer/orders"
    return _forward_to_api("POST", path, data=payload)


@orders_bp.post("/customer/orders/session/<session_id>/request-check")
def request_customer_check(session_id: str):
    """PROXY: Customer requests the check for a session."""
    path = f"/api/customer/orders/session/{session_id}/request-check"
    return _forward_to_api("POST", path)


@orders_bp.post("/orders")
def create_order():
    """PROXY: Create new order."""
    payload = request.get_json(silent=True) or {}
    path = "/api/orders"
    return _forward_to_api("POST", path, data=payload)


@orders_bp.get("/orders/<uuid:order_id>")
def get_order(order_id: UUID):
    """PROXY: Get order details."""
    path = f"/api/orders/{order_id}"
    return _forward_to_api("GET", path)


@orders_bp.post("/orders/<uuid:order_id>/items")
def add_order_item(order_id: UUID):
    """PROXY: Add item to order."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/orders/{order_id}/items"
    return _forward_to_api("POST", path, data=payload)


@orders_bp.delete("/orders/<uuid:order_id>/items/<uuid:item_id>")
def delete_order_item(order_id: UUID, item_id: UUID):
    """PROXY: Delete item from order."""
    path = f"/api/orders/{order_id}/items/{item_id}"
    return _forward_to_api("DELETE", path)


@orders_bp.post("/orders/send-confirmation")
def send_order_confirmation():
    """PROXY: Send order confirmation email."""
    payload = request.get_json(silent=True) or {}
    path = "/api/orders/send-confirmation"
    return _forward_to_api("POST", path, data=payload)
