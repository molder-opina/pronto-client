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

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

orders_bp = Blueprint("client_orders", __name__)


@orders_bp.get("/customer/orders")
def get_customer_orders():
    """PROXY: Get orders for customer (historial)."""
    path = "/api/customer/orders"
    return forward_to_api("GET", path, stream=True)


@orders_bp.post("/customer/orders")
def create_customer_order():
    """PROXY: Create customer order (session-scoped client flow)."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customer/orders"
    return forward_to_api("POST", path, data=payload, stream=True)


@orders_bp.post("/customer/orders/session/<session_id>/request-check")
def request_customer_check(session_id: str):
    """PROXY: Customer requests the check for a session."""
    path = f"/api/customer/orders/session/{session_id}/request-check"
    return forward_to_api("POST", path, stream=True)


@orders_bp.post("/orders")
def create_order():
    """PROXY: Create new order."""
    payload = request.get_json(silent=True) or {}
    path = "/api/orders"
    return forward_to_api("POST", path, data=payload, stream=True)


@orders_bp.get("/orders/<uuid:order_id>")
def get_order(order_id: UUID):
    """PROXY: Get order details."""
    path = f"/api/orders/{order_id}"
    return forward_to_api("GET", path, stream=True)


@orders_bp.post("/orders/<uuid:order_id>/items")
def add_order_item(order_id: UUID):
    """PROXY: Add item to order."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/orders/{order_id}/items"
    return forward_to_api("POST", path, data=payload, stream=True)


@orders_bp.delete("/orders/<uuid:order_id>/items/<uuid:item_id>")
def delete_order_item(order_id: UUID, item_id: UUID):
    """PROXY: Delete item from order."""
    path = f"/api/orders/{order_id}/items/{item_id}"
    return forward_to_api("DELETE", path, stream=True)


@orders_bp.post("/orders/send-confirmation")
def send_order_confirmation():
    """PROXY: Send order confirmation email."""
    payload = request.get_json(silent=True) or {}
    path = "/api/orders/send-confirmation"
    return forward_to_api("POST", path, data=payload, stream=True)
