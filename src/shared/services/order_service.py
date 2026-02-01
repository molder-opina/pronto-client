"""
Domain logic around orders for the employee portal.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from shared.constants import (
    CLIENT_CANCELABLE_STATUSES,
    NON_CANCELABLE_STATUSES,
    OPEN_ORDER_STATUSES,
    ORDER_TRANSITIONS,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Roles,
    SessionStatus,
)
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import (
    Customer,
    DiningSession,
    Employee,
    MenuItem,
    Notification,
    Order,
    OrderItem,
    OrderItemModifier,
    Table,
    WaiterCall,
)
from shared.serializers import serialize_dining_session, serialize_order
from shared.services.notifications_service import (
    notify_session_payment,
)
from shared.services.payment_providers.base_provider import PaymentError
from shared.services.payment_providers.payment_gateway import process_payment
from shared.services.waiter_call_service import get_waiter_assignment_from_dining_session
from shared.services.waiter_table_assignment_service import (
    assign_tables_to_waiter,
    get_table_assignment,
)
from shared.supabase.realtime import emit_session_status_change, emit_waiter_call

logger = get_logger(__name__)
CHECKOUT_CALL_NOTE = "checkout_request"
ACTIVE_WAITER_STATUSES = {
    OrderStatus.NEW.value,
    OrderStatus.QUEUED.value,
    OrderStatus.PREPARING.value,
    OrderStatus.READY.value,
    OrderStatus.DELIVERED.value,
    OrderStatus.AWAITING_PAYMENT.value,
}
GENERIC_CUSTOMER_NAMES = {
    "INVITADO",
    "CLIENTE ANONIMO",
    "CLIENTE ANÓNIMO",
    "ANONIMO",
    "ANÓNIMO",
    "CLIENTE",
}


def _resolve_customer_display_name(customer: Customer | None) -> str:
    if not customer:
        return "Cliente"
    name = (customer.name or "").strip()
    email = (customer.email or "").strip()
    if not name and email:
        return email
    if email and name.upper() in GENERIC_CUSTOMER_NAMES:
        return email
    return name or email or "Cliente"


def _order_requires_kitchen(order: Order) -> bool:
    for item in order.items:
        if not item.menu_item or not getattr(item.menu_item, "is_quick_serve", False):
            return True
    return False


def _get_employee_preference(employee: Employee, key: str, default: any) -> any:
    """Get a preference value from employee's preferences JSON."""
    try:
        preferences = json.loads(employee.preferences or "{}")
        return preferences.get(key, default)
    except (json.JSONDecodeError, TypeError):
        return default


def _set_employee_preference(employee: Employee, key: str, value: any) -> None:
    """Set a preference value in employee's preferences JSON."""
    try:
        preferences = json.loads(employee.preferences or "{}")
    except (json.JSONDecodeError, TypeError):
        preferences = {}
    preferences[key] = value
    employee.preferences = json.dumps(preferences)


def _normalize_status_value(status_value: str) -> str:
    return status_value


def _resolve_order_status(order: Order) -> OrderStatus | None:
    normalized = _normalize_status_value(order.workflow_status)
    try:
        return OrderStatus(normalized)
    except ValueError:
        return None


def _apply_transition_side_effects(
    order: Order,
    action: str,
    actor_id: int | None,
    payload: dict,
) -> None:
    now = datetime.utcnow()

    # Send notifications based on action
    try:
        from shared.notification_stream_service import notify_cashiers, notify_chefs

        if action == "accept_or_queue":
            # Send notification to chefs when order is queued
            table_number = order.session.table_number if order.session else "N/A"
            notify_chefs(
                "new_order_chef",
                "Nueva orden para preparar",
                f"Orden #{order.id} - Mesa {table_number}",
                {"order_id": order.id, "table_number": table_number},
                priority="high",
            )
        elif action == "mark_awaiting_payment":
            # Send notification to cashiers when order awaits payment
            table_number = order.session.table_number if order.session else "N/A"
            notify_cashiers(
                "awaiting_payment",
                "Pago pendiente",
                f"Orden #{order.id} - Mesa {table_number} lista para pago",
                {"order_id": order.id, "table_number": table_number},
                priority="high",
            )
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Error sending notification: {e}")

    if action == "accept_or_queue":
        if not actor_id:
            raise ValueError("waiter_id es requerido para aceptar la orden")
        order.waiter_id = actor_id
        order.accepted_at = now
        if hasattr(order, "waiter_accepted_at"):
            order.waiter_accepted_at = now

    elif action == "kitchen_start":
        if not actor_id:
            raise ValueError("chef_id es requerido para iniciar cocina")
        order.chef_id = actor_id
        if hasattr(order, "chef_accepted_at"):
            order.chef_accepted_at = now

    elif action == "kitchen_complete":
        if hasattr(order, "ready_at"):
            order.ready_at = now

    elif action == "deliver":
        if not actor_id:
            raise ValueError("delivery_waiter_id es requerido para entregar")
        order.delivery_waiter_id = actor_id
        if hasattr(order, "delivered_at"):
            order.delivered_at = now

    elif action == "mark_awaiting_payment":
        if hasattr(order, "check_requested_at"):
            order.check_requested_at = now

    elif action in {"pay", "pay_direct"}:
        payment_method = payload.get("payment_method")
        if not payment_method:
            raise ValueError("payment_method es requerido para pagar")
        valid_methods = {method.value for method in PaymentMethod}
        if payment_method not in valid_methods:
            raise ValueError("payment_method inválido")
        order.payment_method = payment_method
        order.payment_reference = payload.get("payment_reference")
        if payload.get("payment_meta") is not None:
            order.payment_meta = json.dumps(payload.get("payment_meta"))
        if hasattr(order, "paid_at"):
            order.paid_at = now
        if hasattr(order, "payment_status"):
            order.payment_status = PaymentStatus.PAID.value

    elif action == "cancel":
        if hasattr(order, "payment_status"):
            order.payment_status = PaymentStatus.UNPAID.value
        if order.workflow_status in {OrderStatus.NEW.value, OrderStatus.QUEUED.value}:
            order.waiter_id = None
            order.accepted_at = None
            if hasattr(order, "waiter_accepted_at"):
                order.waiter_accepted_at = None
            order.chef_id = None


def _append_justification(order: Order, actor_scope: str, justification: str) -> None:
    note_line = f"[{actor_scope}] {justification}"
    current_notes = order.notes or ""
    order.notes = f"{current_notes}\n{note_line}" if current_notes else note_line


def _transition_order_in_session(
    db_session,
    *,
    order_id: int,
    to_status: OrderStatus,
    actor_scope: str,
    actor_id: int | None = None,
    payload: dict | None = None,
    session_id_expected: int | None = None,
    commit: bool = True,
) -> tuple[dict, HTTPStatus, Order | None]:
    payload = payload or {}

    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            joinedload(Order.items).joinedload(OrderItem.menu_item),
            joinedload(Order.session).joinedload(DiningSession.orders),
            joinedload(Order.customer),
            joinedload(Order.waiter),
            joinedload(Order.chef),
            joinedload(Order.delivery_waiter),
            joinedload(Order.history),
        )
        .with_for_update(of=Order)
    )
    order = db_session.scalar(stmt)
    if not order:
        return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND, None

    if session_id_expected and order.session_id != session_id_expected:
        return {"error": "La orden no pertenece a esta cuenta"}, HTTPStatus.FORBIDDEN, order

    current_status = _resolve_order_status(order)
    if not current_status:
        return {"error": "Estado actual inválido"}, HTTPStatus.BAD_REQUEST, order

    if current_status == to_status:
        scope = "client" if actor_scope == "client" else "employee"
        return serialize_order(order, scope=scope), HTTPStatus.OK, order

    transition_key = (current_status, to_status)
    policy = ORDER_TRANSITIONS.get(transition_key)
    if not policy:
        return (
            {"error": f"Transición inválida: {current_status.value} → {to_status.value}"},
            HTTPStatus.BAD_REQUEST,
            order,
        )

    if actor_scope not in policy["allowed_scopes"]:
        return {"error": "Scope no autorizado para esta acción"}, HTTPStatus.FORBIDDEN, order

    if current_status in NON_CANCELABLE_STATUSES and current_status != to_status:
        return {"error": "Estado final inmutable"}, HTTPStatus.CONFLICT, order

    if actor_scope == "client" and to_status == OrderStatus.CANCELLED:
        if current_status not in CLIENT_CANCELABLE_STATUSES:
            return (
                {"error": "No puedes cancelar: la orden ya está en preparación"},
                HTTPStatus.FORBIDDEN,
                order,
            )

    if policy.get("requires_justification"):
        justification = (payload.get("justification") or "").strip()
        if not justification:
            return {"error": "Esta acción requiere justificación"}, HTTPStatus.BAD_REQUEST, order
        _append_justification(order, actor_scope, justification)

    action = policy["action"]
    if action == "skip_kitchen" and _order_requires_kitchen(order):
        return {"error": "La orden requiere cocina"}, HTTPStatus.CONFLICT, order

    try:
        _apply_transition_side_effects(order, action, actor_id, payload)
    except ValueError as exc:
        return {"error": str(exc)}, HTTPStatus.BAD_REQUEST, order

    requires_waiter = to_status in {
        OrderStatus.QUEUED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.DELIVERED,
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.PAID,
    }
    if requires_waiter and not order.waiter_id:
        return {"error": "waiter_id es requerido"}, HTTPStatus.BAD_REQUEST, order

    if to_status == OrderStatus.PAID:
        if not order.payment_method or not getattr(order, "paid_at", None):
            return {"error": "Pago incompleto"}, HTTPStatus.BAD_REQUEST, order

    order.mark_status(to_status.value)

    if commit:
        db_session.add(order)
        db_session.commit()

    scope = "client" if actor_scope == "client" else "employee"
    return serialize_order(order, scope=scope), HTTPStatus.OK, order


def transition_order(
    order_id: int,
    to_status: OrderStatus,
    actor_scope: str,
    actor_id: int | None = None,
    *,
    payload: dict | None = None,
) -> tuple[dict, HTTPStatus]:
    with get_session() as db_session:
        response, status, _order = _transition_order_in_session(
            db_session,
            order_id=order_id,
            to_status=to_status,
            actor_scope=actor_scope,
            actor_id=actor_id,
            payload=payload,
            commit=True,
        )
        return response, status


def _auto_assign_table_on_order_accept(
    session_obj, order_id: int, session_id: int, table_number: str | None, waiter_id: int
) -> None:
    """
    Auto-assign table to waiter when accepting an order.
    Also assigns all pending orders from the same session to this waiter.

    Args:
        session_obj: SQLAlchemy session
        order_id: ID of the order being accepted
        session_id: ID of the dining session (passed directly to avoid detached instance errors)
        table_number: Table number (passed directly to avoid detached instance errors)
        waiter_id: ID of the waiter accepting the order
    """
    try:
        if not session_id:
            logger.info(f"Order {order_id} has no session_id, skipping auto-assign")
            return

        if not table_number:
            logger.info(f"Order {order_id} has no table_number, skipping auto-assign")
            return

        # Get waiter to check auto-assign preference
        waiter = session_obj.get(Employee, waiter_id)
        if not waiter:
            return

        # Check if auto-assign is enabled (default: True)
        auto_assign_enabled = _get_employee_preference(
            waiter, "auto_assign_table_on_order_accept", True
        )
        if not auto_assign_enabled:
            logger.info(f"Auto-assign disabled for waiter {waiter_id}, skipping table assignment")
            return

        # Find the table by table_number
        table = (
            session_obj.execute(
                select(Table).where(Table.table_number == table_number, Table.is_active)
            )
            .scalars()
            .first()
        )

        if not table:
            logger.warning(f"Table {table_number} not found, cannot auto-assign")
            return

        # Store table ID before it might become detached
        table_id = table.id

        # Check if table is already assigned to this waiter
        existing_assignment = get_table_assignment(table_id)
        if existing_assignment and existing_assignment["waiter_id"] == waiter_id:
            logger.info(f"Table {table_number} already assigned to waiter {waiter_id}")
        else:
            # Assign table to waiter
            result, status = assign_tables_to_waiter(waiter_id, [table_id])
            if status == HTTPStatus.OK:
                logger.info(f"Auto-assigned table {table_number} to waiter {waiter_id}")
            else:
                logger.warning(
                    f"Failed to auto-assign table {table_number} to waiter {waiter_id}: {result}"
                )

        # Assign all pending orders from this session to the waiter
        # Use session_id directly to avoid detached instance error
        pending_orders = (
            session_obj.execute(
                select(Order).where(
                    Order.session_id == session_id,
                    Order.workflow_status == OrderStatus.NEW.value,
                    Order.id != order_id,  # Exclude the current order
                )
            )
            .scalars()
            .all()
        )

        for pending_order in pending_orders:
            pending_order.waiter_id = waiter_id
            logger.info(f"Auto-assigned pending order {pending_order.id} to waiter {waiter_id}")
    except Exception as e:
        # Log the error but don't fail the order acceptance
        logger.error(
            f"Error in _auto_assign_table_on_order_accept for order {order_id}: {e}", exc_info=True
        )
        # Don't raise - we don't want to fail the order acceptance if auto-assign fails


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def list_orders(
    include_closed: bool = False, include_delivered: bool = False, page: int = 1, limit: int = 50
) -> dict:
    """
    Lista todas las órdenes con soporte de paginación.

    Args:
        include_closed: Incluir órdenes cerradas
        include_delivered: Incluir órdenes entregadas
        page: Número de página (1-indexed)
        limit: Número de resultados por página (max 100)

    Returns:
        Dict con orders, total, page, total_pages
    """
    page = max(1, page)
    limit = min(max(1, limit), 100)  # Max 100 per page

    with get_session() as session:
        base_stmt = select(Order).options(
            joinedload(Order.items).joinedload(OrderItem.menu_item),
            joinedload(Order.customer),
            joinedload(Order.session),
            joinedload(Order.history),
            joinedload(Order.waiter),
            joinedload(Order.chef),
            joinedload(Order.delivery_waiter),
        )

        # Apply filters
        if not include_closed:
            active_statuses = [status.value for status in OPEN_ORDER_STATUSES]
            if include_delivered:
                active_statuses.append(OrderStatus.DELIVERED.value)
            base_stmt = base_stmt.where(Order.workflow_status.in_(active_statuses))

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = session.execute(count_stmt).scalar() or 0

        # Apply pagination
        offset = (page - 1) * limit
        stmt = base_stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)

        orders = session.execute(stmt).unique().scalars().all()

        logger.info(f"Listed {len(orders)} orders (page {page}/{limit}, total {total})")

        total_pages = (total + limit - 1) // limit if total > 0 else 1

        return {
            "orders": [serialize_order(order, session=session) for order in orders],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }


def accept_or_queue(
    order_id: int, waiter_id: int, actor_scope: str = "waiter"
) -> tuple[dict, HTTPStatus]:
    response, status = transition_order(
        order_id=order_id,
        to_status=OrderStatus.QUEUED,
        actor_scope=actor_scope,
        actor_id=waiter_id,
    )
    if status != HTTPStatus.OK:
        return response, status

    requires_kitchen = response.get("requires_kitchen")
    if requires_kitchen is False:
        return transition_order(
            order_id=order_id,
            to_status=OrderStatus.READY,
            actor_scope="system",
        )

    if requires_kitchen is True:
        return response, status

    with get_session() as session:
        order = session.get(Order, order_id)
        if order and not _order_requires_kitchen(order):
            return transition_order(
                order_id=order_id,
                to_status=OrderStatus.READY,
                actor_scope="system",
            )

    return response, status


def kitchen_start(
    order_id: int, chef_id: int, actor_scope: str = "chef"
) -> tuple[dict, HTTPStatus]:
    return transition_order(
        order_id=order_id,
        to_status=OrderStatus.PREPARING,
        actor_scope=actor_scope,
        actor_id=chef_id,
    )


def kitchen_complete(order_id: int, actor_scope: str = "chef") -> tuple[dict, HTTPStatus]:
    return transition_order(
        order_id=order_id,
        to_status=OrderStatus.READY,
        actor_scope=actor_scope,
    )


def mark_awaiting_payment(order_id: int, actor_scope: str = "cashier") -> tuple[dict, HTTPStatus]:
    return transition_order(
        order_id=order_id,
        to_status=OrderStatus.AWAITING_PAYMENT,
        actor_scope=actor_scope,
    )


def pay_order(
    order_id: int,
    payment_method: str,
    actor_scope: str = "cashier",
    *,
    payment_reference: str | None = None,
    payment_meta: dict | None = None,
    justification: str | None = None,
) -> tuple[dict, HTTPStatus]:
    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        current_status = _resolve_order_status(order)
        if not current_status:
            return {"error": "Estado actual inválido"}, HTTPStatus.BAD_REQUEST

    to_status = OrderStatus.PAID
    payload = {
        "payment_method": payment_method,
        "payment_reference": payment_reference,
        "payment_meta": payment_meta,
        "justification": justification,
    }

    if current_status == OrderStatus.DELIVERED and actor_scope in {"admin", "system"}:
        if not justification:
            return {"error": "Pago directo requiere justificación"}, HTTPStatus.BAD_REQUEST
        return transition_order(
            order_id=order_id,
            to_status=to_status,
            actor_scope=actor_scope,
            payload=payload,
        )

    if current_status != OrderStatus.AWAITING_PAYMENT:
        return {
            "error": f"No se puede pagar desde estado {current_status.value}"
        }, HTTPStatus.BAD_REQUEST

    return transition_order(
        order_id=order_id,
        to_status=to_status,
        actor_scope=actor_scope,
        payload=payload,
    )


def waiter_accept(order_id: int, waiter_id: int) -> tuple[dict, HTTPStatus]:
    if not waiter_id:
        return {"error": "Selecciona un colaborador"}, HTTPStatus.BAD_REQUEST

    response, status = accept_or_queue(order_id, waiter_id, actor_scope="waiter")
    if status != HTTPStatus.OK:
        return response, status

    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            return response, status

        session_id = order.session_id
        table_number = None
        if session_id:
            dining_session = session.get(DiningSession, session_id)
            if dining_session:
                table_number = dining_session.table_number

        _auto_assign_table_on_order_accept(session, order.id, session_id, table_number, waiter_id)
        session.commit()

    logger.info(f"Waiter {waiter_id} accepted order {order_id}")
    return response, status


def chef_start(order_id: int, chef_id: int) -> tuple[dict, HTTPStatus]:
    if not chef_id:
        return {"error": "Selecciona un colaborador"}, HTTPStatus.BAD_REQUEST
    return kitchen_start(order_id, chef_id, actor_scope="chef")


def chef_ready(order_id: int) -> tuple[dict, HTTPStatus]:
    return kitchen_complete(order_id, actor_scope="chef")


def deliver_order(order_id: int, waiter_id: int) -> tuple[dict, HTTPStatus]:
    if not waiter_id:
        return {"error": "Selecciona un colaborador"}, HTTPStatus.BAD_REQUEST
    return transition_order(
        order_id=order_id,
        to_status=OrderStatus.DELIVERED,
        actor_scope="waiter",
        actor_id=waiter_id,
    )


def deliver_order_items(
    order_id: int, item_ids: list[int], employee_id: int
) -> tuple[dict, HTTPStatus]:
    """
    Entregar items específicos de una orden (entrega parcial).

    Args:
        order_id: ID de la orden
        item_ids: Lista de IDs de OrderItem a marcar como entregados
        employee_id: ID del empleado que entrega los items

    Returns:
        Tuple con la orden serializada y el status HTTP
    """
    if not employee_id:
        return {"error": "Selecciona un colaborador"}, HTTPStatus.BAD_REQUEST

    if not item_ids:
        return {"error": "Debes seleccionar al menos un item"}, HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        # Cargar la orden con todas sus relaciones
        order = (
            db_session.query(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.menu_item),
                joinedload(Order.customer),
                joinedload(Order.session),
            )
            .filter(Order.id == order_id)
            .first()
        )

        if order is None:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        # Verificar que la orden esté lista para entrega
        if order.workflow_status not in [OrderStatus.READY.value, OrderStatus.DELIVERED.value]:
            return {"error": "La orden aún no está lista para entregar"}, HTTPStatus.CONFLICT

        now = datetime.utcnow()
        delivered_count = 0

        # Marcar los items seleccionados como entregados
        for item in order.items:
            if item.id in item_ids and not item.is_fully_delivered:
                item.delivered_quantity = item.quantity
                item.is_fully_delivered = True
                item.delivered_at = now
                item.delivered_by_employee_id = employee_id
                delivered_count += 1
                db_session.add(item)

        if delivered_count == 0:
            return {"error": "Ningún item fue entregado"}, HTTPStatus.BAD_REQUEST

        # Verificar si todos los items de la orden fueron entregados
        all_delivered = all(item.is_fully_delivered for item in order.items)

        if all_delivered:
            # Si todos los items están entregados, marcar la orden completa como entregada
            order.delivery_waiter_id = employee_id
            order.delivered_at = now
            order.mark_status(OrderStatus.DELIVERED.value)
            order.payment_status = PaymentStatus.AWAITING_TIP.value
            db_session.add(order)
            logger.info(f"Order {order_id}: All items delivered, order marked as delivered")
        else:
            # La orden está en entrega parcial
            logger.info(f"Order {order_id}: Partial delivery - {delivered_count} items delivered")

        db_session.commit()

        return serialize_order(order), HTTPStatus.OK


def get_order_delivery_status(order_id: int) -> tuple[dict, HTTPStatus]:
    """
    Obtener el estado de entrega de todos los items de una orden.

    Returns:
        {
            "order_id": int,
            "workflow_status": str,
            "items": [
                {
                    "id": int,
                    "menu_item_id": int,
                    "menu_item_name": str,
                    "quantity": int,
                    "delivered_quantity": int,
                    "is_fully_delivered": bool,
                    "delivered_at": str | null,
                    "delivered_by_employee_id": int | null
                }
            ],
            "all_items_delivered": bool
        }
    """
    with get_session() as db_session:
        order = (
            db_session.query(Order)
            .options(joinedload(Order.items).joinedload(OrderItem.menu_item))
            .filter(Order.id == order_id)
            .first()
        )

        if order is None:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        items_data = []
        for item in order.items:
            items_data.append(
                {
                    "id": item.id,
                    "menu_item_id": item.menu_item_id,
                    "menu_item_name": item.menu_item.name if item.menu_item else "Unknown",
                    "quantity": item.quantity,
                    "delivered_quantity": item.delivered_quantity,
                    "is_fully_delivered": item.is_fully_delivered,
                    "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
                    "delivered_by_employee_id": item.delivered_by_employee_id,
                }
            )

        all_delivered = all(item.is_fully_delivered for item in order.items)

        return {
            "order_id": order.id,
            "workflow_status": order.workflow_status,
            "items": items_data,
            "all_items_delivered": all_delivered,
        }, HTTPStatus.OK


def cancel_order(
    order_id: int,
    actor_scope: str = "employee",
    *,
    session_id: int | None = None,
    reason: str | None = None,
    actor_id: int | None = None,
) -> tuple[dict, HTTPStatus]:
    """Cancel an order using policy engine and enforce scope rules."""
    from shared.services.business_config_service import get_config_value

    try:
        store_reason_config = get_config_value("store_cancel_reason", "true")
        store_reason = str(store_reason_config).lower() not in {"false", "0", "no"}
    except Exception:
        store_reason = True

    payload = {"justification": reason} if reason else {}

    with get_session() as db_session:
        response, status, order = _transition_order_in_session(
            db_session,
            order_id=order_id,
            to_status=OrderStatus.CANCELLED,
            actor_scope=actor_scope,
            actor_id=actor_id,
            payload=payload,
            session_id_expected=session_id,
            commit=False,
        )
        if status != HTTPStatus.OK or not order:
            return response, status

        if store_reason and reason and reason not in (order.notes or ""):
            _append_justification(order, actor_scope, reason)

        dining_session = order.session
        if dining_session:
            dining_session.recompute_totals()
            has_active_orders = any(
                child.workflow_status != OrderStatus.CANCELLED.value
                for child in dining_session.orders
            )

            if not has_active_orders:
                dining_session.status = SessionStatus.PAID.value
                dining_session.closed_at = datetime.utcnow()
                dining_session.payment_method = None
                dining_session.payment_reference = None
                dining_session.total_paid = Decimal("0")
                dining_session.tip_amount = Decimal("0")

            db_session.add(dining_session)

        db_session.add(order)
        scope = "client" if actor_scope == "client" else "employee"
        result = serialize_order(order, scope=scope)
        db_session.commit()

        logger.info("Order %s cancelled by %s", order_id, actor_scope)
        return result, HTTPStatus.OK


def prepare_checkout(session_id: int) -> tuple[dict, HTTPStatus]:
    with get_session() as session:
        dining_session = session.get(DiningSession, session_id)
        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND
        if dining_session.status not in {"open", "awaiting_tip", "awaiting_payment"}:
            return {"error": "La cuenta ya se encuentra cerrada"}, HTTPStatus.CONFLICT

        # Marcar la cuenta como lista para propina/pago y registrar la solicitud de cuenta
        now = datetime.utcnow()
        dining_session.status = "awaiting_tip"
        dining_session.tip_requested_at = now
        # check_requested_at se usa para el panel de caja (sesiones pendientes de pago)
        # y para ordenarlas por hora de solicitud. Al usar prepare_checkout
        # desde el cliente o empleados, lo sincronizamos con la misma marca de tiempo.
        dining_session.check_requested_at = now
        session.add(dining_session)
        waiter_call_id = _ensure_checkout_waiter_call(session, dining_session)

        # Reload session to ensure it is attached
        dining_session = session.get(DiningSession, session_id)

        # Extract data needed for events/response before commit
        table_number = (
            dining_session.table_number
            or (dining_session.table.table_number if dining_session.table else None)
            or "N/A"
        )
        session_id_val = dining_session.id

        data = serialize_dining_session(dining_session)
        if waiter_call_id:
            data["waiter_call_id"] = waiter_call_id

        session.commit()

        # Emitir evento de cambio de estado para notificar a meseros/cajeros
        try:
            emit_session_status_change(
                session_id=session_id_val,
                status="awaiting_tip",
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        return data, HTTPStatus.OK


def _ensure_checkout_waiter_call(db_session, dining_session: DiningSession) -> int | None:
    """
    Create and broadcast a waiter call when a customer requests the check,
    avoiding duplicates if one is already pending.
    """
    if dining_session is None:
        return None

    table_number = (
        dining_session.table_number
        or (dining_session.table.table_number if dining_session.table else None)
        or "N/A"
    )

    active_order_numbers = [
        order.id
        for order in dining_session.orders
        if order.workflow_status != OrderStatus.CANCELLED.value
    ]
    waiter_id, waiter_name = get_waiter_assignment_from_dining_session(dining_session)

    existing_call = db_session.execute(
        select(WaiterCall).where(
            WaiterCall.session_id == dining_session.id,
            WaiterCall.status == "pending",
            WaiterCall.notes == CHECKOUT_CALL_NOTE,
        )
    ).scalar_one_or_none()

    if existing_call:
        try:
            emit_waiter_call(
                call_id=existing_call.id,
                session_id=dining_session.id,
                table_number=table_number,
                status="pending",
                call_type=CHECKOUT_CALL_NOTE,
                order_numbers=active_order_numbers,
                waiter_id=waiter_id,
                waiter_name=waiter_name,
                created_at=existing_call.created_at,
            )
        except Exception as exc:
            logger.error("Error re-emitting waiter call for checkout request: %s", exc)
        return existing_call.id

    waiter_call = WaiterCall(
        session_id=dining_session.id,
        table_number=table_number,
        status="pending",
        notes=CHECKOUT_CALL_NOTE,
    )
    db_session.add(waiter_call)
    db_session.flush()
    waiter_call_id = waiter_call.id

    notification = Notification(
        notification_type="waiter_call",
        recipient_type="all_waiters",
        recipient_id=None,
        title="Mesa solicitando cuenta",
        message=f"La mesa {table_number} pidió la cuenta",
        data=json.dumps(
            {
                "table_number": table_number,
                "session_id": dining_session.id,
                "waiter_call_id": waiter_call_id,
                "type": "checkout_request",
            }
        ),
        priority="high",
    )
    db_session.add(notification)

    try:
        emit_waiter_call(
            call_id=waiter_call_id,
            session_id=dining_session.id,
            table_number=table_number,
            status="pending",
            call_type=CHECKOUT_CALL_NOTE,
            order_numbers=active_order_numbers,
            waiter_id=waiter_id,
            waiter_name=waiter_name,
            created_at=waiter_call.created_at,
        )
    except Exception as exc:
        logger.error("Error emitting waiter call for checkout request: %s", exc)

    return waiter_call_id


def update_order_notes(
    order_id: int, notes: str | None, employee_id: int | None
) -> tuple[dict, HTTPStatus]:
    """Update waiter-facing notes for an active order."""
    cleaned_notes = (notes or "").strip()

    with get_session() as session:
        order = session.get(Order, order_id)
        if order is None:
            return {"error": "Orden no encontrada"}, HTTPStatus.NOT_FOUND

        if order.workflow_status not in ACTIVE_WAITER_STATUSES:
            return {"error": "Solo puedes anotar órdenes activas"}, HTTPStatus.BAD_REQUEST

        order.notes = cleaned_notes or None
        order.updated_at = datetime.utcnow()
        session.add(order)

        logger.info("Employee %s updated notes for order %s", employee_id or "unknown", order_id)

        return {
            "order_id": order.id,
            "notes": order.notes,
            "waiter_notes": order.notes,
            "customer_notes": order.session.notes if order.session else None,
        }, HTTPStatus.OK


def calculate_tip_amount(
    subtotal: float, tip_percentage: float | None = None, tip_amount: float | None = None
) -> Decimal:
    """Calculate tip amount from percentage or use fixed amount."""
    if tip_amount is not None:
        return _to_decimal(tip_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif tip_percentage is not None:
        subtotal_decimal = _to_decimal(subtotal)
        percentage_decimal = _to_decimal(tip_percentage) / Decimal("100")
        return (subtotal_decimal * percentage_decimal).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        return Decimal("0")


def apply_tip(
    session_id: int, tip_amount: float | None = None, tip_percentage: float | None = None
) -> tuple[dict, HTTPStatus]:
    """Apply tip to a session, either by fixed amount or percentage."""
    with get_session() as session:
        dining_session = session.get(DiningSession, session_id)
        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND
        if dining_session.status not in {"open", "awaiting_tip", "awaiting_payment"}:
            return {"error": "La cuenta ya se encuentra cerrada"}, HTTPStatus.CONFLICT

        # Calculate tip amount from percentage or use fixed amount
        tip_decimal = calculate_tip_amount(
            subtotal=float(dining_session.subtotal),
            tip_percentage=tip_percentage,
            tip_amount=tip_amount,
        )

        dining_session.tip_amount = tip_decimal
        dining_session.tip_confirmed_at = datetime.utcnow()
        dining_session.recompute_totals()
        dining_session.status = "awaiting_payment"
        session.add(dining_session)
        session.commit()

        # Emit session status change event
        table_number = (
            dining_session.table_number
            or (dining_session.table.table_number if dining_session.table else None)
            or "N/A"
        )
        try:
            emit_session_status_change(
                session_id=dining_session.id,
                status="awaiting_payment",
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        data = serialize_dining_session(dining_session)
        return data, HTTPStatus.OK


def update_customer_contact(
    session_id: int,
    email: str | None = None,
    phone: str | None = None,
) -> tuple[dict, HTTPStatus]:
    """Update customer contact information for ticket delivery."""
    with get_session() as session:
        dining_session = session.get(DiningSession, session_id)
        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND

        customer = dining_session.customer
        updated = False

        if email and email.strip():
            # Actualizar solo si el email actual es temporal
            if customer.email.startswith("anonimo+"):
                customer.email = email.strip()
                updated = True

        if phone and phone.strip():
            customer.phone = phone.strip()
            updated = True

        if not updated:
            return {
                "error": "No se proporcionó información de contacto válida"
            }, HTTPStatus.BAD_REQUEST

        session.flush()

        return {
            "message": "Información de contacto actualizada",
            "customer": {
                "name": customer.name,
                "email": customer.email if not customer.email.startswith("anonimo+") else None,
                "phone": customer.phone,
            },
        }, HTTPStatus.OK


def finalize_payment(
    session_id: int,
    payment_method: str,
    tip_amount: float | None = None,
    tip_percentage: float | None = None,
    payment_reference: str | None = None,
    customer_email: str | None = None,
    customer_phone: str | None = None,
) -> tuple[dict, HTTPStatus]:
    """Finalize payment for a session, optionally applying tip and updating customer contact."""
    with get_session() as session:
        from sqlalchemy.orm import joinedload

        # Cargar session con todas las relaciones para evitar DetachedInstanceError
        dining_session = (
            session.query(DiningSession)
            .options(
                joinedload(DiningSession.orders),
                joinedload(DiningSession.customer),
                joinedload(DiningSession.table),
            )
            .filter(DiningSession.id == session_id)
            .first()
        )

        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND
        if dining_session.status == "paid":
            return {"error": "La cuenta ya fue pagada"}, HTTPStatus.CONFLICT

        # Update customer contact if provided (for anonymous purchases)
        if customer_email or customer_phone:
            customer = dining_session.customer
            if customer_email and customer_email.strip():
                # Solo actualizar si el email actual es temporal
                if customer.email.startswith("anonimo+"):
                    customer.email = customer_email.strip()
            if customer_phone and customer_phone.strip():
                customer.phone = customer_phone.strip()

        # Apply tip if provided (either by amount or percentage)
        if tip_amount is not None or tip_percentage is not None:
            tip_decimal = calculate_tip_amount(
                subtotal=float(dining_session.subtotal),
                tip_percentage=tip_percentage,
                tip_amount=tip_amount,
            )
            dining_session.tip_amount = tip_decimal
            dining_session.tip_confirmed_at = datetime.utcnow()
        elif dining_session.tip_confirmed_at is None:
            dining_session.tip_requested_at = datetime.utcnow()

        dining_session.recompute_totals()

        # Validate payment method using enum
        valid_payment_methods = [
            PaymentMethod.STRIPE.value,
            PaymentMethod.CLIP.value,
            PaymentMethod.CASH.value,
            PaymentMethod.CARD.value,
        ]
        if payment_method not in valid_payment_methods:
            return {
                "error": f"Método de pago inválido. Métodos soportados: {', '.join(valid_payment_methods)}"
            }, HTTPStatus.BAD_REQUEST

        # Métodos que requieren confirmación del mesero
        REQUIRES_CONFIRMATION = {PaymentMethod.CASH.value, PaymentMethod.CARD.value}

        # Process payment using unified gateway
        try:
            # Para cash y card, usar cash provider (no hay procesamiento externo)
            provider_name = payment_method
            if payment_method == PaymentMethod.CARD.value:
                # Card se procesa como cash (confirmación física del mesero)
                provider_name = PaymentMethod.CASH.value

            payment_result = process_payment(
                provider_name=provider_name,
                session=dining_session,
                payment_reference=payment_reference,
            )
            payment_reference = payment_result.reference
        except PaymentError as exc:
            return {"error": str(exc)}, HTTPStatus.BAD_REQUEST

        dining_session.payment_method = payment_method
        dining_session.payment_reference = payment_reference
        dining_session.total_paid = dining_session.total_amount

        # Si requiere confirmación, poner en estado awaiting_payment_confirmation
        # Si no, cerrar directamente
        if payment_method in REQUIRES_CONFIRMATION:
            dining_session.status = SessionStatus.AWAITING_PAYMENT_CONFIRMATION.value
            # No cerrar aún, esperar confirmación del mesero
        else:
            # Stripe y Clip se cierran automáticamente
            dining_session.status = SessionStatus.PAID.value
            dining_session.closed_at = datetime.utcnow()

            # Marcar órdenes como pagadas solo si se cierra
            for order in dining_session.orders:
                order.payment_status = PaymentStatus.PAID.value
                order.payment_method = payment_method
                order.payment_reference = payment_reference
                order.paid_at = datetime.utcnow()
                session.add(order)

            notify_session_payment(dining_session)

        session.add(dining_session)

        # Serialize BEFORE commit to avoid DetachedInstanceError
        # All relationships were already loaded with joinedload
        data = serialize_dining_session(dining_session)
        data["requires_confirmation"] = payment_method in REQUIRES_CONFIRMATION

        session.commit()

        # Emit session status change event
        table_number = (
            dining_session.table_number
            or (dining_session.table.table_number if dining_session.table else None)
            or "N/A"
        )
        try:
            emit_session_status_change(
                session_id=dining_session.id,
                status=dining_session.status,
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        return data, HTTPStatus.OK


def get_dashboard_metrics() -> dict[str, float]:
    with get_session() as session:
        total_sales = session.scalar(select(func.coalesce(func.sum(DiningSession.total_paid), 0)))
        open_sessions = session.scalar(
            select(func.count()).where(DiningSession.status != SessionStatus.PAID.value)
        )
        pending_orders = session.scalar(
            select(func.count()).where(
                Order.workflow_status.in_([s.value for s in OPEN_ORDER_STATUSES])
            )
        )
        ready_orders = session.scalar(
            select(func.count()).where(Order.workflow_status == OrderStatus.READY.value)
        )
        active_orders = session.scalar(
            select(func.count()).where(Order.workflow_status != OrderStatus.DELIVERED.value)
        )
        active_waiters = session.scalar(
            select(func.count()).where(
                Employee.role == Roles.WAITER.value,
                Employee.is_active.is_(True),
            )
        )
        tip_totals = session.execute(
            select(
                func.coalesce(func.sum(DiningSession.tip_amount), 0),
                func.coalesce(func.sum(DiningSession.subtotal), 0),
            ).where(DiningSession.status == SessionStatus.PAID.value)
        ).one()
        total_tip = float(tip_totals[0] or 0)
        total_subtotal = float(tip_totals[1] or 0)
        avg_tip_ratio = (total_tip / total_subtotal) if total_subtotal > 0 else 0.0
        happy_clients_score = (
            round(min(5.0, max(0.0, avg_tip_ratio * 5.0 / 0.20)), 1) if avg_tip_ratio else 4.5
        )

        # Filter for today's top items
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        top_items = session.execute(
            select(MenuItem.name, func.sum(OrderItem.quantity).label("qty"))
            .join(OrderItem.menu_item)
            .join(OrderItem.order)
            .where(Order.created_at >= today_start)
            .group_by(MenuItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(3)
        ).all()

        return {
            "total_sales": float(total_sales or 0),
            "open_sessions": int(open_sessions or 0),
            "pending_orders": int(pending_orders or 0),
            "ready_orders": int(ready_orders or 0),
            "active_orders": int(active_orders or 0),
            "active_waiters": int(active_waiters or 0),
            "happy_clients_score": float(happy_clients_score),
            "avg_tip_percentage": float(avg_tip_ratio * 100) if avg_tip_ratio else 0.0,
            "top_items": [{"name": name, "quantity": int(qty)} for name, qty in top_items],
        }


def generate_ticket(session_id: int) -> tuple[str, HTTPStatus]:
    with get_session() as session:
        dining_session = (
            session.execute(
                select(DiningSession)
                .options(
                    joinedload(DiningSession.orders)
                    .joinedload(Order.items)
                    .joinedload(OrderItem.menu_item),
                    joinedload(DiningSession.orders)
                    .joinedload(Order.items)
                    .joinedload(OrderItem.modifiers)
                    .joinedload(OrderItemModifier.modifier),
                    joinedload(DiningSession.customer),
                )
                .where(DiningSession.id == session_id)
            )
            .unique()
            .scalars()
            .one_or_none()
        )
        if dining_session is None:
            return "Cuenta no encontrada", HTTPStatus.NOT_FOUND

        dining_session.recompute_totals()

        customer_name = dining_session.customer.name if dining_session.customer else "Cliente"
        table_label = dining_session.table_number or "N/A"

        lines = [
            f"Ticket #{dining_session.id}",
            f"Cliente: {customer_name}",
            f"Mesa: {table_label}",
            "---",
        ]
        sorted_orders = sorted(
            dining_session.orders,
            key=lambda order: (order.created_at or datetime.min, order.id),
        )
        for order in sorted_orders:
            lines.append(f"--- Orden #{order.id} ---")
            if order.workflow_status:
                lines.append(f"Estado: {order.workflow_status}")
            if order.created_at:
                lines.append(f"Hora: {order.created_at.strftime('%H:%M')}")
            for item in order.items:
                item_name = item.menu_item.name if item.menu_item else "Producto"
                item_total = Decimal(str(item.unit_price)) * item.quantity
                lines.append(f"  {item.quantity}x {item_name}  {float(item_total):.2f}")

                for modifier in item.modifiers:
                    mod_name = modifier.modifier.name if modifier.modifier else "Modificador"
                    mod_total = Decimal(str(modifier.unit_price_adjustment)) * modifier.quantity
                    lines.append(f"    + {mod_name} x{modifier.quantity}  {float(mod_total):.2f}")

            if order.total_amount is not None:
                lines.append(f"Total orden: {float(order.total_amount):.2f}")
            lines.append("---")
        lines.append("--- Totales ---")
        lines.append(f"Subtotal: {float(dining_session.subtotal):.2f}")
        lines.append(f"IVA: {float(dining_session.tax_amount):.2f}")
        lines.append(f"Propina: {float(dining_session.tip_amount):.2f}")
        lines.append(f"Total: {float(dining_session.total_amount):.2f}")
        if dining_session.status == "paid":
            lines.append(f"Pagado con: {dining_session.payment_method}")
            lines.append(f"Referencia: {dining_session.payment_reference}")
        return "\n".join(lines), HTTPStatus.OK


def get_waiter_tips(employee_id: int, include_pending: bool = False) -> dict[str, object]:
    """Get tips summary for a specific waiter/employee."""
    with get_session() as session:
        from shared.models import Employee

        employee = session.get(Employee, employee_id)
        if employee is None:
            return {"error": "Empleado no encontrado"}

        # Get all sessions where this employee was involved as waiter or delivery_waiter
        query = (
            select(DiningSession)
            .join(DiningSession.orders)
            .where(
                (Order.waiter_id == employee_id) | (Order.delivery_waiter_id == employee_id),
                DiningSession.status == "paid",
                DiningSession.tip_amount > 0,
            )
            .distinct()
        )

        sessions = session.execute(query).scalars().all()

        # Calculate tips by session
        tips_by_session = []
        total_tips = Decimal(0)

        for dining_session in sessions:
            # Count how many waiters were involved in this session
            waiter_ids = set()
            for order in dining_session.orders:
                if order.waiter_id:
                    waiter_ids.add(order.waiter_id)
                if order.delivery_waiter_id:
                    waiter_ids.add(order.delivery_waiter_id)

            # Split tip among all waiters involved
            num_waiters = len(waiter_ids) if waiter_ids else 1
            tip_share = _to_decimal(dining_session.tip_amount) / num_waiters

            tips_by_session.append(
                {
                    "session_id": dining_session.id,
                    "table_number": dining_session.table_number,
                    "closed_at": dining_session.closed_at.isoformat()
                    if dining_session.closed_at
                    else None,
                    "total_tip": float(dining_session.tip_amount),
                    "tip_share": float(tip_share),
                    "num_waiters": num_waiters,
                    "total_amount": float(dining_session.total_amount),
                }
            )
            total_tips += tip_share

        return {
            "employee_id": employee_id,
            "employee_name": employee.name,
            "total_tips": float(total_tips),
            "sessions_count": len(tips_by_session),
            "tips_by_session": tips_by_session,
        }


def list_closed_sessions(hours: int | None = None) -> tuple[dict, HTTPStatus]:
    """
    Get list of closed sessions within the configured history period.

    Args:
        hours: Number of hours to look back. If None, uses business config value (default 24).

    Returns:
        Tuple of (response dict, HTTP status)
    """
    from datetime import timedelta

    from shared.services.business_config_service import get_config_value

    # Get history period from config or use provided value
    if hours is None:
        hours = get_config_value("closed_sessions_history_hours", 24)

    def normalize_customer_email(email: str | None) -> str | None:
        if not email:
            return None
        cleaned = email.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if lowered in {"none", "null", "undefined"}:
            return None
        if lowered.startswith("anonimo+") or "@temp.local" in lowered or "@pronto.local" in lowered:
            return None
        return cleaned

    def resolve_session_customer_email(dining_session: DiningSession) -> str | None:
        email = normalize_customer_email(
            dining_session.customer.email if dining_session.customer else None
        )
        if email:
            return email
        orders = sorted(
            dining_session.orders,
            key=lambda order: order.created_at or datetime.min,
            reverse=True,
        )
        for order in orders:
            email = normalize_customer_email(getattr(order, "customer_email", None))
            if email:
                return email
            email = normalize_customer_email(order.customer.email if order.customer else None)
            if email:
                return email
        return None

    with get_session() as session:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        stmt = (
            select(DiningSession)
            .options(
                joinedload(DiningSession.customer),
                joinedload(DiningSession.orders).joinedload(Order.items),
            )
            .where(
                DiningSession.status == SessionStatus.PAID.value,
                DiningSession.closed_at >= cutoff_time,
            )
            .order_by(DiningSession.closed_at.desc())
        )

        closed_sessions = session.execute(stmt).unique().scalars().all()

        sessions_data = []
        for ds in closed_sessions:
            resolved_email = resolve_session_customer_email(ds)
            sessions_data.append(
                {
                    "id": ds.id,
                    "customer_name": ds.customer.name if ds.customer else "Cliente",
                    "customer_email": resolved_email,
                    "table_number": ds.table_number,
                    "opened_at": ds.opened_at.isoformat() if ds.opened_at else None,
                    "closed_at": ds.closed_at.isoformat() if ds.closed_at else None,
                    "subtotal": float(ds.subtotal),
                    "tax_amount": float(ds.tax_amount),
                    "tip_amount": float(ds.tip_amount),
                    "total_amount": float(ds.total_amount),
                    "payment_method": ds.payment_method,
                    "payment_reference": ds.payment_reference,
                    "orders_count": len(ds.orders),
                }
            )

        return {
            "closed_sessions": sessions_data,
            "history_hours": hours,
            "count": len(sessions_data),
        }, HTTPStatus.OK


def confirm_payment(session_id: int) -> tuple[dict, HTTPStatus]:
    """
    Confirmar pago de una sesión que está en awaiting_payment_confirmation.
    Esto cierra la sesión y marca las órdenes como pagadas.
    """
    with get_session() as session:
        from sqlalchemy.orm import joinedload

        # Cargar session con todas las relaciones para evitar DetachedInstanceError
        dining_session = (
            session.query(DiningSession)
            .options(
                joinedload(DiningSession.orders),
                joinedload(DiningSession.customer),
                joinedload(DiningSession.table),
            )
            .filter(DiningSession.id == session_id)
            .first()
        )

        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND

        if dining_session.status != SessionStatus.AWAITING_PAYMENT_CONFIRMATION.value:
            return {
                "error": "Esta cuenta no está pendiente de confirmación de pago"
            }, HTTPStatus.CONFLICT

        if not dining_session.payment_method:
            return {"error": "No se encontró método de pago registrado"}, HTTPStatus.BAD_REQUEST

        # Confirmar el pago: cerrar sesión y marcar órdenes como pagadas
        dining_session.status = SessionStatus.PAID.value
        dining_session.closed_at = datetime.utcnow()
        dining_session.payment_confirmed_at = datetime.utcnow()

        # Marcar todas las órdenes como pagadas
        for order in dining_session.orders:
            order.payment_status = PaymentStatus.PAID.value
            order.payment_method = dining_session.payment_method
            order.payment_reference = dining_session.payment_reference
            order.paid_at = datetime.utcnow()
            session.add(order)

        session.add(dining_session)

        # Serializar y extraer datos ANTES del commit para evitar DetachedInstanceError
        data = serialize_dining_session(dining_session)
        table_number = (
            dining_session.table_number
            or (dining_session.table.table_number if dining_session.table else None)
            or "N/A"
        )

        session.commit()

        # Enviar notificación de email después del commit
        try:
            notify_session_payment(dining_session)
        except Exception as exc:
            logger.warning("Failed to send payment notification: %s", exc)

        # Emit session status change event (después del commit)
        try:
            emit_session_status_change(
                session_id=session_data_for_notification["id"],
                status=SessionStatus.PAID.value,
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        # Enviar notificación usando datos extraídos (no el objeto desconectado)
        try:
            logger.info(
                "Notificación de pago enviada",
                extra={"channels": ["email"], "payload": session_data_for_notification},
            )
        except Exception as exc:
            logger.warning("Failed to send payment notification: %s", exc)

        return data, HTTPStatus.OK


def confirm_partial_payment(session_id: int, order_ids: list[int]) -> tuple[dict, HTTPStatus]:
    """
    Confirmar pago parcial de órdenes específicas de una sesión.

    Permite pagar una o más órdenes de una sesión sin cerrarla completamente.
    La sesión solo se cierra cuando todas sus órdenes están pagadas.

    Args:
        session_id: ID de la sesión
        order_ids: Lista de IDs de órdenes a pagar

    Returns:
        Tuple de (response dict, HTTP status)
    """
    with get_session() as session:
        from sqlalchemy.orm import joinedload

        # Cargar session con todas las relaciones para evitar DetachedInstanceError
        dining_session = (
            session.query(DiningSession)
            .options(
                joinedload(DiningSession.orders),
                joinedload(DiningSession.customer),
                joinedload(DiningSession.table),
            )
            .filter(DiningSession.id == session_id)
            .first()
        )

        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND

        if dining_session.status != SessionStatus.AWAITING_PAYMENT_CONFIRMATION.value:
            return {
                "error": "Esta cuenta no está pendiente de confirmación de pago"
            }, HTTPStatus.CONFLICT

        if not dining_session.payment_method:
            return {"error": "No se encontró método de pago registrado"}, HTTPStatus.BAD_REQUEST

        # Validar que todas las órdenes pertenecen a esta sesión
        session_order_ids = {order.id for order in dining_session.orders}
        invalid_orders = set(order_ids) - session_order_ids
        if invalid_orders:
            return {
                "error": f"Las órdenes {invalid_orders} no pertenecen a esta sesión"
            }, HTTPStatus.BAD_REQUEST

        # Marcar las órdenes seleccionadas como pagadas
        paid_count = 0
        for order in dining_session.orders:
            if order.id in order_ids:
                order.payment_status = PaymentStatus.PAID.value
                order.payment_method = dining_session.payment_method
                order.payment_reference = dining_session.payment_reference
                order.paid_at = datetime.utcnow()
                session.add(order)
                paid_count += 1

        # Verificar si todas las órdenes de la sesión están pagadas
        all_paid = all(
            order.payment_status == PaymentStatus.PAID.value for order in dining_session.orders
        )

        # Si todas las órdenes están pagadas, cerrar la sesión
        if all_paid:
            dining_session.status = SessionStatus.PAID.value
            dining_session.closed_at = datetime.utcnow()
            dining_session.payment_confirmed_at = datetime.utcnow()
            session_status_msg = "closed"
        else:
            # Mantener la sesión abierta pero marcar que tiene pagos parciales
            dining_session.payment_confirmed_at = datetime.utcnow()
            session_status_msg = "partial_payment"

        session.add(dining_session)

        # Serializar y extraer datos ANTES del commit para evitar DetachedInstanceError
        data = serialize_dining_session(dining_session)
        data["paid_orders_count"] = paid_count
        data["total_orders_count"] = len(dining_session.orders)
        data["session_status"] = session_status_msg

        table_number = (
            dining_session.table_number
            or (dining_session.table.table_number if dining_session.table else None)
            or "N/A"
        )
        session_id_value = dining_session.id

        session_data_for_notification = {
            "id": dining_session.id,
            "customer_email": dining_session.customer.email if dining_session.customer else None,
            "customer_phone": dining_session.customer.phone if dining_session.customer else None,
            "total_amount": float(dining_session.total_amount)
            if dining_session.total_amount
            else 0.0,
            "payment_method": dining_session.payment_method,
            "payment_reference": dining_session.payment_reference,
        }

        session.commit()

        # Emit session status change event (después del commit)
        try:
            status_to_emit = (
                SessionStatus.PAID.value
                if all_paid
                else SessionStatus.AWAITING_PAYMENT_CONFIRMATION.value
            )
            emit_session_status_change(
                session_id=session_id_value,
                status=status_to_emit,
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        # Si la sesión se cerró completamente, enviar notificación
        if all_paid:
            try:
                logger.info(
                    "Notificación de pago enviada",
                    extra={"channels": ["email"], "payload": session_data_for_notification},
                )
            except Exception as exc:
                logger.warning("Failed to send payment notification: %s", exc)

        return data, HTTPStatus.OK


def resend_ticket(session_id: int, email: str) -> tuple[dict, HTTPStatus]:
    """
    Resend ticket to customer via email.

    Args:
        session_id: DiningSession ID
        email: Email address to send ticket to

    Returns:
        Tuple of (response dict, HTTP status)
    """
    from shared.services.email_service import send_ticket_email

    with get_session() as session:
        dining_session = (
            session.execute(
                select(DiningSession)
                .options(
                    joinedload(DiningSession.orders)
                    .joinedload(Order.items)
                    .joinedload(OrderItem.menu_item),
                    joinedload(DiningSession.customer),
                )
                .where(DiningSession.id == session_id)
            )
            .unique()
            .scalars()
            .one_or_none()
        )

        if dining_session is None:
            return {"error": "Cuenta no encontrada"}, HTTPStatus.NOT_FOUND

        if dining_session.status != SessionStatus.PAID.value:
            return {
                "error": "Solo se pueden reenviar tickets de cuentas cerradas"
            }, HTTPStatus.BAD_REQUEST

        # Generate ticket content
        ticket_text, _ = generate_ticket(session_id)

        # Send email
        email_sent = send_ticket_email(email, ticket_text, session_id)

        if email_sent:
            logger.info(f"Ticket sent for session {session_id} to {email}")
            return {
                "message": "Ticket enviado exitosamente",
                "session_id": session_id,
                "email": email,
            }, HTTPStatus.OK
        else:
            # Email service disabled or failed - return success anyway with warning
            logger.warning(f"Email not sent for session {session_id} (service disabled or error)")
            return {
                "message": "Ticket generado. El envío por email está deshabilitado.",
                "session_id": session_id,
                "email": email,
                "email_sent": False,
            }, HTTPStatus.OK


def list_all_sessions(include_paid: bool = False) -> tuple[dict, HTTPStatus]:
    """
    Get list of all dining sessions with detailed information.

    Args:
        include_paid: If True, includes paid sessions. Default False.

    Returns:
        Tuple of (response dict with sessions list, HTTP status)
    """
    with get_session() as session:
        stmt = (
            select(DiningSession)
            .options(
                joinedload(DiningSession.customer),
                joinedload(DiningSession.orders),
            )
            .order_by(DiningSession.opened_at.desc())
        )

        if not include_paid:
            stmt = stmt.where(
                DiningSession.status.notin_([SessionStatus.PAID.value, SessionStatus.CLOSED.value])
            )

        sessions = session.execute(stmt).unique().scalars().all()

        sessions_data = []
        for ds in sessions:
            # Get last order time
            last_order_time = None
            active_orders_count = 0

            if ds.orders:
                # Find the most recent order creation time
                order_times = [order.created_at for order in ds.orders if order.created_at]
                if order_times:
                    last_order_time = max(order_times)

                # Count active orders (not cancelled)
                active_orders_count = sum(
                    1 for order in ds.orders if order.workflow_status != OrderStatus.CANCELLED.value
                )

            sessions_data.append(
                {
                    "id": ds.id,
                    "table_number": ds.table_number or "N/A",
                    "status": ds.status,
                    "customer_name": _resolve_customer_display_name(ds.customer),
                    "customer_email": ds.customer.email if ds.customer else None,
                    "opened_at": ds.opened_at.isoformat() if ds.opened_at else None,
                    "closed_at": ds.closed_at.isoformat() if ds.closed_at else None,
                    "last_order_at": last_order_time.isoformat() if last_order_time else None,
                    "orders_count": len(ds.orders),
                    "active_orders_count": active_orders_count,
                    "subtotal": float(ds.subtotal),
                    "total_amount": float(ds.total_amount),
                }
            )

        return {"sessions": sessions_data, "count": len(sessions_data)}, HTTPStatus.OK


def close_session(session_id: int) -> tuple[dict, HTTPStatus]:
    """
    Close a dining session and mark all its orders as cancelled.

    Args:
        session_id: ID of the session to close

    Returns:
        Tuple of (response dict, HTTP status)
    """
    with get_session() as session:
        dining_session = session.get(DiningSession, session_id)
        if dining_session is None:
            return {"error": "Sesión no encontrada"}, HTTPStatus.NOT_FOUND

        if dining_session.status == SessionStatus.PAID.value:
            return {"error": "La sesión ya está cerrada y pagada"}, HTTPStatus.CONFLICT

        # Cancel all non-cancelled orders
        cancelled_count = 0
        for order in dining_session.orders:
            if order.workflow_status != OrderStatus.CANCELLED.value:
                order.mark_status(OrderStatus.CANCELLED.value)
                order.payment_status = PaymentStatus.UNPAID.value
                order.waiter_id = None
                order.waiter_accepted_at = None
                order.chef_id = None
                order.chef_accepted_at = None
                order.delivery_waiter_id = None
                order.ready_at = None
                order.delivered_at = None
                order.updated_at = datetime.utcnow()
                session.add(order)
                cancelled_count += 1

        # Close the session
        dining_session.status = SessionStatus.CLOSED.value
        dining_session.closed_at = datetime.utcnow()
        dining_session.recompute_totals()

        session.add(dining_session)
        session.commit()

        # Emit session status change event
        table_number = dining_session.table_number or "N/A"
        try:
            emit_session_status_change(
                session_id=dining_session.id,
                status=SessionStatus.CLOSED.value,
                table_number=table_number,
            )
        except Exception as exc:
            logger.warning("Failed to emit session status change: %s", exc)

        logger.info(f"Session {session_id} closed with {cancelled_count} orders cancelled")

        return {
            "message": "Sesión cerrada exitosamente",
            "session_id": session_id,
            "cancelled_orders": cancelled_count,
        }, HTTPStatus.OK


def resolve_session_customer_email(session: DiningSession) -> str | None:
    """
    Get effective email for a dining session.

    Priority:
    1. Session customer.email (if not temporary)
    2. Order customer_email (if not temporary)
    3. None

    Args:
        session: DiningSession object

    Returns:
        Email address or None if no valid email found
    """

    # Normalize email function
    def _normalize(email: str | None) -> str | None:
        if not email:
            return None
        cleaned = email.strip().lower()
        # Skip temporary/anonymous emails
        if (
            not cleaned
            or cleaned in {"none", "null", "undefined"}
            or cleaned.startswith("anonimo+")
            or "@temp.local" in cleaned
            or "@pronto.local" in cleaned
        ):
            return None
        return cleaned

    # Priority 1: Session customer email
    if session.customer:
        email = _normalize(session.customer.email)
        if email:
            return email

    # Priority 2: Check orders for customer_email
    for order in sorted(
        session.orders, key=lambda o: o.created_at or session.opened_at, reverse=True
    ):
        if hasattr(order, "customer_email"):
            email = _normalize(order.customer_email)
            if email:
                return email
        if order.customer:
            email = _normalize(order.customer.email)
            if email:
                return email

    return None
