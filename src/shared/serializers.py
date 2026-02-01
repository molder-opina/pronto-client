"""
Serializers for consistent API responses.
"""

from datetime import datetime, timedelta
from typing import Any

from shared.constants import ORDER_STATUS_META_DEFAULT, OrderStatus
from shared.db import get_session
from shared.models import (
    Customer,
    DiningSession,
    Employee,
    MenuCategory,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusLabel,
)


def _safe_float(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


_LABEL_CACHE_TTL = timedelta(minutes=5)
_LABEL_CACHE: dict[str, tuple[dict[str, str], datetime]] = {}


def resolve_status_meta(status_key: str, scope: str = "employee", session=None) -> dict[str, str]:
    # Use status key directly (assumed canonical)
    normalized = status_key
    cached = _LABEL_CACHE.get(normalized)
    if cached:
        cached_data, cached_at = cached
        if datetime.utcnow() - cached_at < _LABEL_CACHE_TTL:
            return _build_status_response(cached_data, scope)

    try:
        if session:
            label = session.get(OrderStatusLabel, normalized)
            if label:
                data = {
                    "client_label": label.client_label,
                    "employee_label": label.employee_label,
                    "admin_desc": label.admin_desc,
                }
                _LABEL_CACHE[normalized] = (data, datetime.utcnow())
                return _build_status_response(data, scope)
        else:
            with get_session() as new_session:
                label = new_session.get(OrderStatusLabel, normalized)
                if label:
                    data = {
                        "client_label": label.client_label,
                        "employee_label": label.employee_label,
                        "admin_desc": label.admin_desc,
                    }
                    _LABEL_CACHE[normalized] = (data, datetime.utcnow())
                    return _build_status_response(data, scope)
    except Exception:
        pass

    fallback = ORDER_STATUS_META_DEFAULT.get(
        normalized,
        {
            "client_label": normalized,
            "employee_label": normalized,
            "admin_desc": normalized,
        },
    )
    return _build_status_response(fallback, scope)


def _build_status_response(data: dict[str, str], scope: str) -> dict[str, str]:
    status_display = data["client_label"] if scope == "client" else data["employee_label"]

    return {
        **data,
        "status_display": status_display,
    }


def invalidate_status_label_cache(status_key: str | None = None) -> None:
    if status_key:
        _LABEL_CACHE.pop(status_key, None)
        return
    _LABEL_CACHE.clear()


def serialize_employee(employee: Employee) -> dict[str, Any]:
    """Serialize Employee model."""
    return {
        "id": employee.id,
        "name": employee.name,
        "email": employee.email,
        "role": employee.role,
        "is_active": employee.is_active,
        "created_at": employee.created_at.isoformat(),
    }


def serialize_customer(
    customer: Customer | None, mask_anonymous: bool = True
) -> dict[str, Any] | None:
    """Serialize Customer model."""
    if customer is None:
        return None

    email = customer.email
    if mask_anonymous and email.startswith("anonimo+"):
        email = None

    return {
        "id": customer.id,
        "name": customer.name,
        "email": email,
        "phone": customer.phone,
        "physical_description": customer.physical_description,
        "avatar": customer.avatar,
    }


def serialize_menu_item(item: MenuItem) -> dict[str, Any]:
    """Serialize MenuItem model."""
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "price": float(item.price),
        "is_available": item.is_available,
        "image_path": item.image_path,
        "category_id": item.category_id,
        "is_quick_serve": getattr(item, "is_quick_serve", False),
    }


def serialize_menu_category(category: MenuCategory) -> dict[str, Any]:
    """Serialize MenuCategory model."""
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "display_order": category.display_order,
        "items": [serialize_menu_item(item) for item in category.items],
    }


def serialize_order_item(order_item: OrderItem) -> dict[str, Any]:
    """Serialize OrderItem model."""
    # Serialize modifiers if present
    modifiers = []
    if hasattr(order_item, "modifiers") and order_item.modifiers:
        for mod in order_item.modifiers:
            if mod.modifier:
                modifiers.append(
                    {
                        "name": mod.modifier.name,
                        "price": _safe_float(mod.unit_price_adjustment),
                        "quantity": mod.quantity,
                    }
                )

    return {
        "id": order_item.id,
        "menu_item_id": order_item.menu_item_id,
        "name": order_item.menu_item.name if order_item.menu_item else "Item",
        "quantity": order_item.quantity,
        "unit_price": _safe_float(order_item.unit_price),
        "is_quick_serve": order_item.menu_item.is_quick_serve if order_item.menu_item else False,
        "delivered_quantity": order_item.delivered_quantity,
        "is_fully_delivered": order_item.is_fully_delivered,
        "delivered_at": order_item.delivered_at.isoformat() if order_item.delivered_at else None,
        "delivered_by_employee_id": order_item.delivered_by_employee_id,
        "modifiers": modifiers,
    }


def serialize_order(order: Order, scope: str = "employee", session=None) -> dict[str, Any]:
    """Serialize Order model."""
    customer_notes = order.session.notes if order.session else None
    waiter_notes = order.notes
    requires_kitchen = any(
        not (item.menu_item and getattr(item.menu_item, "is_quick_serve", False))
        for item in order.items
    )

    status_key = order.workflow_status
    status_meta = resolve_status_meta(status_key, scope, session=session)

    return {
        "id": order.id,
        "session_id": order.session_id,
        "workflow_status": order.workflow_status,
        "status_display": status_meta["status_display"],
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "payment_reference": order.payment_reference,
        "payment_meta": order.payment_meta,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "notes": waiter_notes,
        "customer_notes": customer_notes,
        "waiter_notes": waiter_notes,
        "subtotal": _safe_float(order.subtotal),
        "tax_amount": _safe_float(order.tax_amount),
        "tip_amount": _safe_float(order.tip_amount),
        "total_amount": _safe_float(order.total_amount),
        "waiter_id": order.waiter_id,
        "waiter_name": order.waiter.name if order.waiter else None,
        "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
        "chef_id": order.chef_id,
        "chef_name": order.chef.name if order.chef else None,
        "delivery_waiter_id": order.delivery_waiter_id,
        "delivery_waiter_name": order.delivery_waiter.name if order.delivery_waiter else None,
        "created_at": order.created_at.isoformat(),
        "session": {
            "id": order.session.id,
            "status": order.session.status,
            "table_number": order.session.table_number,
            "opened_at": order.session.opened_at.isoformat(),
            "closed_at": order.session.closed_at.isoformat() if order.session.closed_at else None,
            "notes": order.session.notes,
            "tip_amount": _safe_float(order.session.tip_amount),
            "total_amount": _safe_float(order.session.total_amount),
            "totals": {
                "subtotal": _safe_float(order.session.subtotal),
                "tax_amount": _safe_float(order.session.tax_amount),
                "tip_amount": _safe_float(order.session.tip_amount),
                "total_amount": _safe_float(order.session.total_amount),
            },
        },
        "customer": serialize_customer(order.customer),
        "items": [serialize_order_item(item) for item in order.items],
        "requires_kitchen": requires_kitchen,
        "history": [
            {
                "status": event.status,
                "changed_at": event.changed_at.isoformat() if event.changed_at else None,
            }
            for event in order.history
        ],
    }


def serialize_dining_session(dining_session: DiningSession) -> dict[str, Any]:
    """Serialize DiningSession model."""
    dining_session.recompute_totals()

    return {
        "id": dining_session.id,
        "status": dining_session.status,
        "table_number": dining_session.table_number,
        "customer": serialize_customer(dining_session.customer),
        "totals": {
            "subtotal": _safe_float(dining_session.subtotal),
            "tax_amount": _safe_float(dining_session.tax_amount),
            "tip_amount": _safe_float(dining_session.tip_amount),
            "total_amount": _safe_float(getattr(dining_session, "total_amount", None)),
            "total_paid": _safe_float(getattr(dining_session, "total_paid", None)),
        },
        "opened_at": dining_session.opened_at.isoformat(),
        "closed_at": dining_session.closed_at.isoformat() if dining_session.closed_at else None,
        "payment_method": dining_session.payment_method,
        "payment_reference": dining_session.payment_reference,
    }


def paginated_response(
    items: list[Any],
    total: int,
    page: int,
    limit: int,
) -> dict[str, Any]:
    """
    Create a standardized paginated response.

    Args:
        items: List of serialized items for current page
        total: Total count of items across all pages
        page: Current page number (1-indexed)
        limit: Items per page

    Returns:
        Standardized response dict with data and meta
    """
    total_pages = (total + limit - 1) // limit if limit > 0 else 0

    return {
        "data": items,
        "meta": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


def success_response(data: Any, message: str | None = None) -> dict[str, Any]:
    """Create a standardized success response."""
    response = {"status": "success", "data": data, "error": None}
    if message:
        response["message"] = message
    return response


def error_response(error: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a standardized error response."""
    response = {"status": "error", "data": None, "error": error}
    if details:
        response["details"] = details
    return response
