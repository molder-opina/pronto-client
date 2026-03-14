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

from flask import Blueprint, Response, request, session

from ._upstream import forward_to_api

orders_bp = Blueprint("client_orders", __name__)


def _extract_dining_session_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    direct_candidates = (
        payload.get("session_id"),
        payload.get("dining_session_id"),
        payload.get("session_uuid"),
    )
    for candidate in direct_candidates:
        value = str(candidate or "").strip()
        if value:
            return value

    nested_data = payload.get("data")
    if isinstance(nested_data, dict):
        nested_value = _extract_dining_session_id(nested_data)
        if nested_value:
            return nested_value

    nested_session = payload.get("session")
    if isinstance(nested_session, dict):
        for key in ("id", "session_id", "dining_session_id"):
            value = str(nested_session.get(key) or "").strip()
            if value:
                return value

    return ""


def _sync_dining_session_from_proxy_response(proxy_response: tuple[object, int] | Response) -> None:
    response_body: object
    status_code: int
    if isinstance(proxy_response, tuple):
        response_body, status_code = proxy_response
    else:
        response_body = proxy_response
        status_code = int(getattr(proxy_response, "status_code", 0) or 0)

    if status_code < 200 or status_code >= 400:
        return

    if not isinstance(response_body, Response):
        return

    payload = response_body.get_json(silent=True)
    dining_session_id = _extract_dining_session_id(payload)
    if not dining_session_id:
        return

    session["dining_session_id"] = dining_session_id
    session.permanent = False


@orders_bp.get("/customer/orders")
def get_customer_orders():
    """PROXY: Get orders for customer (historial)."""
    path = "/api/customer/orders"
    return forward_to_api("GET", path, stream=True)


@orders_bp.get("/customer/orders/<path:order_id>")
def get_customer_order(order_id: str):
    """PROXY: Get a specific customer order."""
    path = f"/api/customer/orders/{order_id}"
    return forward_to_api("GET", path, stream=True)


@orders_bp.post("/customer/orders")
def create_customer_order():
    """PROXY: Create customer order (session-scoped client flow)."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customer/orders"
    proxy_response = forward_to_api("POST", path, data=payload, stream=False)
    _sync_dining_session_from_proxy_response(proxy_response)
    return proxy_response


@orders_bp.get("/customer/orders/cart")
def get_customer_cart():
    """PROXY: Get customer draft cart."""
    path = "/api/customer/orders/cart"
    return forward_to_api("GET", path, stream=True)


@orders_bp.put("/customer/orders/cart")
def upsert_customer_cart():
    """PROXY: Upsert customer draft cart."""
    payload = request.get_json(silent=True) or {}
    path = "/api/customer/orders/cart"
    return forward_to_api("PUT", path, data=payload, stream=False)


@orders_bp.post("/customer/orders/cart/abandon")
def abandon_customer_cart():
    """PROXY: Mark customer cart as abandoned."""
    path = "/api/customer/orders/cart/abandon"
    return forward_to_api("POST", path, stream=False)


@orders_bp.post("/customer/orders/<path:order_id>/cancel")
def cancel_customer_order(order_id: str):
    """PROXY: Cancel a specific customer order."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customer/orders/{order_id}/cancel"
    return forward_to_api("POST", path, data=payload, stream=False)


@orders_bp.post("/customer/orders/<path:order_id>/modify")
def modify_customer_order(order_id: str):
    """PROXY: Modify a specific customer order."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customer/orders/{order_id}/modify"
    return forward_to_api("POST", path, data=payload, stream=False)


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
    proxy_response = forward_to_api("POST", path, data=payload, stream=False)
    _sync_dining_session_from_proxy_response(proxy_response)
    return proxy_response


@orders_bp.get("/orders")
def list_orders():
    """PROXY: List orders (supports session_id query for client tracker)."""
    session_id = (request.args.get("session_id") or "").strip()
    path = "/api/orders/by-session" if session_id else "/api/orders"
    query = request.query_string.decode("utf-8").strip()
    if query:
        path = f"{path}?{query}"
    return forward_to_api("GET", path, stream=True)


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
