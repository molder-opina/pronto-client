"""
Service for handling order modifications.
Supports both customer and waiter-initiated modifications.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus
from typing import Any

from flask import current_app
from sqlalchemy import select

from shared.constants import ModificationInitiator, ModificationStatus, OrderStatus
from shared.db import get_session
from shared.models import (
    MenuItem,
    Modifier,
    Order,
    OrderItem,
    OrderItemModifier,
    OrderModification,
)
from shared.supabase.realtime import emit_custom_event

logger = logging.getLogger(__name__)


class ModificationError(Exception):
    """Raised when a modification operation fails."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def can_customer_modify_order(order: Order) -> bool:
    """
    Check if a customer can modify an order.
    Customers can only modify if the order hasn't been accepted by waiter yet.
    """
    return order.workflow_status == OrderStatus.NEW.value


def create_modification(
    order_id: int,
    changes_data: dict[str, Any],
    initiated_by_role: str,
    customer_id: int | None = None,
    employee_id: int | None = None,
) -> tuple[dict, HTTPStatus]:
    """
    Create a modification request for an order.

    Args:
        order_id: The order to modify
        changes_data: Dict containing items_to_add, items_to_remove, items_to_update
        initiated_by_role: 'customer' or 'waiter'
        customer_id: ID of customer if customer-initiated
        employee_id: ID of employee if waiter-initiated

    Returns:
        Tuple of (response_dict, status_code)
    """
    with get_session() as session:
        # Get the order
        order = session.get(Order, order_id)
        if not order:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        # Validate based on who initiated
        if initiated_by_role == ModificationInitiator.CUSTOMER.value:
            if not can_customer_modify_order(order):
                return {
                    "error": "No puedes modificar esta orden. Ya ha sido aceptada por el mesero."
                }, HTTPStatus.FORBIDDEN

            # Customer-initiated modifications are auto-approved
            status = ModificationStatus.PENDING.value
            auto_apply = True
        else:
            # Waiter-initiated modifications require customer approval
            status = ModificationStatus.PENDING.value
            auto_apply = False

        # Validate changes_data structure
        if not isinstance(changes_data, dict):
            return {"error": "Formato de cambios inválido"}, HTTPStatus.BAD_REQUEST

        # Validate items exist
        items_to_add = changes_data.get("items_to_add", [])
        items_to_remove = changes_data.get("items_to_remove", [])
        changes_data.get("items_to_update", [])

        # Validate menu items exist for items to add
        for item_data in items_to_add:
            menu_item_id = item_data.get("menu_item_id")
            menu_item = session.get(MenuItem, menu_item_id)
            if not menu_item or not menu_item.is_available:
                return {"error": f"Producto {menu_item_id} no disponible"}, HTTPStatus.BAD_REQUEST

        # Validate order items exist for items to remove
        for order_item_id in items_to_remove:
            order_item = session.get(OrderItem, order_item_id)
            if not order_item or order_item.order_id != order_id:
                return {
                    "error": f"Item de orden {order_item_id} no encontrado"
                }, HTTPStatus.BAD_REQUEST

        # Create the modification
        modification = OrderModification(
            order_id=order_id,
            initiated_by_role=initiated_by_role,
            initiated_by_customer_id=customer_id,
            initiated_by_employee_id=employee_id,
            status=status,
            changes_data=json.dumps(changes_data),
        )
        session.add(modification)
        session.flush()

        modification_id = modification.id

        # If customer-initiated, auto-apply the changes
        if auto_apply:
            apply_result = _apply_modification(session, modification, order)
            if apply_result["success"]:
                modification.status = ModificationStatus.APPLIED.value
                modification.applied_at = datetime.utcnow()
            else:
                session.rollback()
                return {"error": apply_result["error"]}, HTTPStatus.INTERNAL_SERVER_ERROR

        session.commit()

        # Send Redis event notification
        try:
            if initiated_by_role == ModificationInitiator.WAITER.value:
                # Notify customer about waiter's modification request
                emit_custom_event(
                    event="modification_requested",
                    data={
                        "modification_id": modification_id,
                        "order_id": order_id,
                        "session_id": order.session_id,
                        "changes": changes_data,
                    },
                    room=f"session_{order.session_id}",
                )
        except Exception as e:
            logger.warning(f"Failed to emit modification event: {e}")

        return {
            "modification_id": modification_id,
            "order_id": order_id,
            "status": modification.status,
            "initiated_by": initiated_by_role,
            "auto_applied": auto_apply,
        }, HTTPStatus.CREATED if auto_apply else HTTPStatus.OK


def approve_modification(
    modification_id: int,
    customer_id: int,
) -> tuple[dict, HTTPStatus]:
    """
    Customer approves a waiter-initiated modification.
    """
    with get_session() as session:
        modification = session.get(OrderModification, modification_id)
        if not modification:
            return {"error": "Modificación no encontrada"}, HTTPStatus.NOT_FOUND

        if modification.status != ModificationStatus.PENDING.value:
            return {"error": f"Modificación ya fue {modification.status}"}, HTTPStatus.BAD_REQUEST

        # Verify this is a waiter-initiated modification
        if modification.initiated_by_role != ModificationInitiator.WAITER.value:
            return {"error": "Esta modificación no requiere aprobación"}, HTTPStatus.BAD_REQUEST

        # Get the order
        order = session.get(Order, modification.order_id)
        if not order:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        # Verify customer owns this order
        if order.customer_id != customer_id:
            return {
                "error": "No tienes permiso para aprobar esta modificación"
            }, HTTPStatus.FORBIDDEN

        # Apply the modification
        json.loads(modification.changes_data)
        apply_result = _apply_modification(session, modification, order)

        if not apply_result["success"]:
            session.rollback()
            return {"error": apply_result["error"]}, HTTPStatus.INTERNAL_SERVER_ERROR

        # Update modification status
        modification.status = ModificationStatus.APPROVED.value
        modification.status = ModificationStatus.APPLIED.value
        modification.reviewed_by_customer_id = customer_id
        modification.reviewed_at = datetime.utcnow()
        modification.applied_at = datetime.utcnow()

        session.commit()

        # Notify employees
        try:
            emit_custom_event(
                event="modification_approved",
                data={
                    "modification_id": modification_id,
                    "order_id": order.id,
                    "session_id": order.session_id,
                },
                room="employees",
            )
        except Exception as e:
            logger.warning(f"Failed to emit modification approved event: {e}")

        return {
            "modification_id": modification_id,
            "status": "approved_and_applied",
            "order_id": order.id,
        }, HTTPStatus.OK


def reject_modification(
    modification_id: int,
    customer_id: int,
    reason: str | None = None,
) -> tuple[dict, HTTPStatus]:
    """
    Customer rejects a waiter-initiated modification.
    """
    with get_session() as session:
        modification = session.get(OrderModification, modification_id)
        if not modification:
            return {"error": "Modificación no encontrada"}, HTTPStatus.NOT_FOUND

        if modification.status != ModificationStatus.PENDING.value:
            return {"error": f"Modificación ya fue {modification.status}"}, HTTPStatus.BAD_REQUEST

        # Verify this is a waiter-initiated modification
        if modification.initiated_by_role != ModificationInitiator.WAITER.value:
            return {"error": "Esta modificación no requiere aprobación"}, HTTPStatus.BAD_REQUEST

        # Get the order
        order = session.get(Order, modification.order_id)
        if not order:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        # Verify customer owns this order
        if order.customer_id != customer_id:
            return {
                "error": "No tienes permiso para rechazar esta modificación"
            }, HTTPStatus.FORBIDDEN

        # Update modification status
        modification.status = ModificationStatus.REJECTED.value
        modification.reviewed_by_customer_id = customer_id
        modification.reviewed_at = datetime.utcnow()

        # Optionally update changes_data with rejection reason
        if reason:
            changes_data = json.loads(modification.changes_data)
            changes_data["rejection_reason"] = reason
            modification.changes_data = json.dumps(changes_data)

        session.commit()

        # Notify employees
        try:
            emit_custom_event(
                event="modification_rejected",
                data={
                    "modification_id": modification_id,
                    "order_id": order.id,
                    "session_id": order.session_id,
                    "reason": reason,
                },
                room="employees",
            )
        except Exception as e:
            logger.warning(f"Failed to emit modification rejected event: {e}")

        return {
            "modification_id": modification_id,
            "status": "rejected",
            "order_id": order.id,
        }, HTTPStatus.OK


def get_modification_details(
    modification_id: int,
) -> tuple[dict, HTTPStatus]:
    """
    Get details of a modification request.
    """
    with get_session() as session:
        modification = session.get(OrderModification, modification_id)
        if not modification:
            return {"error": "Modificación no encontrada"}, HTTPStatus.NOT_FOUND

        changes_data = json.loads(modification.changes_data)

        response = {
            "id": modification.id,
            "order_id": modification.order_id,
            "initiated_by_role": modification.initiated_by_role,
            "status": modification.status,
            "changes": changes_data,
            "created_at": modification.created_at.isoformat() if modification.created_at else None,
            "reviewed_at": modification.reviewed_at.isoformat()
            if modification.reviewed_at
            else None,
            "applied_at": modification.applied_at.isoformat() if modification.applied_at else None,
        }

        return response, HTTPStatus.OK


def _apply_modification(session, modification: OrderModification, order: Order) -> dict[str, Any]:
    """
    Apply the modification changes to the order.
    This is called after approval or automatically for customer-initiated modifications.

    Returns:
        Dict with "success" boolean and optional "error" message
    """
    try:
        changes_data = json.loads(modification.changes_data)
        tax_rate = Decimal(str(current_app.config.get("TAX_RATE", 0.16)))

        # Remove items
        items_to_remove = changes_data.get("items_to_remove", [])
        for order_item_id in items_to_remove:
            order_item = session.get(OrderItem, order_item_id)
            if order_item and order_item.order_id == order.id:
                session.delete(order_item)

        # Update items
        items_to_update = changes_data.get("items_to_update", [])
        for item_update in items_to_update:
            order_item_id = item_update.get("order_item_id")
            new_quantity = item_update.get("quantity")

            order_item = session.get(OrderItem, order_item_id)
            if order_item and order_item.order_id == order.id:
                order_item.quantity = new_quantity

        # Add items
        items_to_add = changes_data.get("items_to_add", [])
        for item_data in items_to_add:
            menu_item_id = item_data.get("menu_item_id")
            quantity = item_data.get("quantity", 1)
            modifiers = item_data.get("modifiers", [])
            special_instructions = item_data.get("special_instructions")

            menu_item = session.get(MenuItem, menu_item_id)
            if not menu_item:
                return {"success": False, "error": f"Menu item {menu_item_id} not found"}

            # Create order item
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=menu_item_id,
                quantity=quantity,
                unit_price=float(menu_item.price),
                special_instructions=special_instructions,
            )
            session.add(order_item)
            session.flush()

            # Add modifiers
            for modifier_data in modifiers:
                modifier_id = modifier_data.get("modifier_id")
                modifier_quantity = modifier_data.get("quantity", 1)

                modifier = session.get(Modifier, modifier_id)
                if modifier:
                    order_item_modifier = OrderItemModifier(
                        order_item_id=order_item.id,
                        modifier_id=modifier_id,
                        quantity=modifier_quantity,
                        unit_price_adjustment=float(modifier.price_adjustment),
                    )
                    session.add(order_item_modifier)

        # Recalculate order totals
        session.flush()
        _recalculate_order_totals(session, order, tax_rate)

        return {"success": True}

    except Exception as e:
        logger.error(f"Error applying modification: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _recalculate_order_totals(session, order: Order, tax_rate: Decimal) -> None:
    """
    Recalculate order subtotal, tax, and total after modifications.
    Uses the new price service to correctly calculate tax based on display mode.
    """
    from shared.services.price_service import calculate_price_breakdown, get_price_display_mode

    # Get price display mode
    price_mode = get_price_display_mode()

    subtotal_base = Decimal("0")  # Subtotal without tax (base prices)

    # Reload items to get fresh data
    order_items = (
        session.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().all()
    )

    for order_item in order_items:
        # Calculate base price for this item
        item_display_price = Decimal(str(order_item.unit_price))
        item_breakdown = calculate_price_breakdown(item_display_price, tax_rate, price_mode)
        item_base_price = item_breakdown["price_base"] * Decimal(str(order_item.quantity))

        # Calculate base price for modifiers
        modifier_base_total = Decimal("0")
        for modifier in order_item.modifiers:
            modifier_display_price = Decimal(str(modifier.unit_price_adjustment)) * Decimal(
                str(modifier.quantity)
            )
            mod_breakdown = calculate_price_breakdown(modifier_display_price, tax_rate, price_mode)
            modifier_base_total += mod_breakdown["price_base"]

        subtotal_base += item_base_price + modifier_base_total

    # Calculate tax on base subtotal
    tax_amount = (subtotal_base * tax_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    total_amount = subtotal_base + tax_amount

    order.subtotal = float(subtotal_base)
    order.tax_amount = float(tax_amount)
    order.total_amount = float(total_amount)

    # Recompute session totals
    if order.session:
        order.session.recompute_totals()
