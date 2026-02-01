"""
Order State Machine - Separa la lógica de transiciones de estado del modelo Order.

Este módulo implementa el patrón State Machine para gestionar las transiciones
de estado de las órdenes de forma controlada y extensible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any

from shared.constants import (
    CLIENT_CANCELABLE_STATUSES,
    NON_CANCELABLE_STATUSES,
    OPEN_ORDER_STATUSES,
    ORDER_TRANSITIONS,
    OrderStatus,
)
from shared.models import Order, OrderStatusHistory


class OrderStateError(Exception):
    """Error raised when a state transition is invalid."""

    def __init__(self, message: str, current_status: OrderStatus, target_status: OrderStatus):
        super().__init__(message)
        self.current_status = current_status
        self.target_status = target_status


class OrderEvent(Enum):
    """Eventos que pueden dispara transiciones de estado."""

    ACCEPT_OR_QUEUE = "accept_or_queue"
    KITCHEN_START = "kitchen_start"
    KITCHEN_COMPLETE = "kitchen_complete"
    DELIVER = "deliver"
    MARK_AWAITING_PAYMENT = "mark_awaiting_payment"
    PAY = "pay"
    PAY_DIRECT = "pay_direct"
    CANCEL = "cancel"


@dataclass
class TransitionContext:
    """Contexto para una transición de estado."""

    order: Order
    event: OrderEvent
    actor_scope: str  # 'waiter', 'chef', 'cashier', 'admin', 'client', 'system'
    actor_id: int | None = None
    payload: dict[str, Any] | None = None
    requires_justification: bool = False
    justification: str | None = None


class OrderStateMachine:
    """
    Máquina de estados para transiciones de órdenes.

    Responsibilities:
    - Validar transiciones permitidas
    - Verificar permisos por scope
    - Aplicar side-effects de transiciones
    - Generar historial de cambios
    """

    def __init__(self):
        self._transition_handlers: dict[tuple[OrderStatus, OrderEvent], callable] = {}
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Registra los handlers para cada transición."""
        self._transition_handlers[(OrderStatus.NEW, OrderEvent.ACCEPT_OR_QUEUE)] = (
            self._handle_accept_or_queue
        )
        self._transition_handlers[(OrderStatus.QUEUED, OrderEvent.KITCHEN_START)] = (
            self._handle_kitchen_start
        )
        self._transition_handlers[(OrderStatus.PREPARING, OrderEvent.KITCHEN_COMPLETE)] = (
            self._handle_kitchen_complete
        )
        self._transition_handlers[(OrderStatus.READY, OrderEvent.DELIVER)] = self._handle_deliver
        self._transition_handlers[(OrderStatus.PREPARING, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.DELIVERED, OrderEvent.MARK_AWAITING_PAYMENT)] = (
            self._handle_mark_awaiting_payment
        )
        self._transition_handlers[(OrderStatus.AWAITING_PAYMENT, OrderEvent.PAY)] = self._handle_pay
        self._transition_handlers[(OrderStatus.DELIVERED, OrderEvent.PAY_DIRECT)] = (
            self._handle_pay_direct
        )
        self._transition_handlers[(OrderStatus.NEW, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.QUEUED, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.PREPARING, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.READY, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.DELIVERED, OrderEvent.CANCEL)] = self._handle_cancel
        self._transition_handlers[(OrderStatus.AWAITING_PAYMENT, OrderEvent.CANCEL)] = (
            self._handle_cancel
        )

    def can_transition(
        self, current_status: OrderStatus, event: OrderEvent, actor_scope: str
    ) -> bool:
        """Verifica si una transición es válida."""
        if current_status in NON_CANCELABLE_STATUSES:
            if event == OrderEvent.CANCEL:
                return False

        transition_key = (current_status, event)
        policy = ORDER_TRANSITIONS.get(transition_key)

        if not policy:
            return False

        if actor_scope not in policy.get("allowed_scopes", []):
            return False

        return True

    def validate_transition(self, context: TransitionContext) -> None:
        """Valida que la transición sea válida."""
        current_status = self._get_status(context.order)

        # Validar que la transición existe
        transition_key = (current_status, context.event)
        policy = ORDER_TRANSITIONS.get(transition_key)

        if not policy:
            raise OrderStateError(
                f"Transición inválida: {current_status.value} → {context.event.value}",
                current_status,
                self._get_target_status(context.event),
            )

        # Validar scope del actor
        if context.actor_scope not in policy.get("allowed_scopes", []):
            raise OrderStateError(
                f"Scope '{context.actor_scope}' no autorizado para esta transición",
                current_status,
                self._get_target_status(context.event),
            )

        # Validar justificación si es requerida
        if policy.get("requires_justification") and not context.justification:
            raise OrderStateError(
                "Esta acción requiere justificación",
                current_status,
                self._get_target_status(context.event),
            )

    def apply_transition(self, context: TransitionContext) -> None:
        """Aplica la transición de estado."""
        self.validate_transition(context)

        current_status = self._get_status(context.order)

        # Buscar el handler específico
        handler = self._transition_handlers.get((current_status, context.event))

        if handler:
            handler(context)
        else:
            # Si no hay handler específico, solo cambiar estado
            self._change_status(context.order, context.event)

        # Registrar en el historial
        target_status = self._get_target_status(context.event)
        context.order.history.append(OrderStatusHistory(status=target_status.value))

    def _get_status(self, order: Order) -> OrderStatus:
        """Obtiene el estado actual de la orden como enum."""
        try:
            return OrderStatus(order.workflow_status)
        except ValueError:
            return OrderStatus.NEW  # Fallback

    def _get_target_status(self, event: OrderEvent) -> OrderStatus:
        """Obtiene el estado objetivo a partir del evento."""
        mapping = {
            OrderEvent.ACCEPT_OR_QUEUE: OrderStatus.QUEUED,
            OrderEvent.KITCHEN_START: OrderStatus.PREPARING,
            OrderEvent.KITCHEN_COMPLETE: OrderStatus.READY,
            OrderEvent.DELIVER: OrderStatus.DELIVERED,
            OrderEvent.MARK_AWAITING_PAYMENT: OrderStatus.AWAITING_PAYMENT,
            OrderEvent.PAY: OrderStatus.PAID,
            OrderEvent.PAY_DIRECT: OrderStatus.PAID,
            OrderEvent.CANCEL: OrderStatus.CANCELLED,
        }
        return mapping[event]

    def _change_status(self, order: Order, event: OrderEvent) -> None:
        """Cambia el estado de la orden."""
        order.workflow_status = self._get_target_status(event).value
        order.updated_at = datetime.utcnow()

    def _handle_accept_or_queue(self, context: TransitionContext) -> None:
        """Maneja la aceptación de una orden."""
        if not context.actor_id:
            raise OrderStateError("waiter_id es requerido para aceptar la orden", None, None)
        context.order.waiter_id = context.actor_id
        context.order.accepted_at = datetime.utcnow()
        if hasattr(context.order, "waiter_accepted_at"):
            context.order.waiter_accepted_at = datetime.utcnow()

    def _handle_kitchen_start(self, context: TransitionContext) -> None:
        """Maneja el inicio de preparación en cocina."""
        if not context.actor_id:
            raise OrderStateError("chef_id es requerido para iniciar cocina", None, None)
        context.order.chef_id = context.actor_id
        if hasattr(context.order, "chef_accepted_at"):
            context.order.chef_accepted_at = datetime.utcnow()

    def _handle_kitchen_complete(self, context: TransitionContext) -> None:
        """Maneja la finalización de preparación."""
        if hasattr(context.order, "ready_at"):
            context.order.ready_at = datetime.utcnow()

    def _handle_deliver(self, context: TransitionContext) -> None:
        """Maneja la entrega de una orden."""
        if not context.actor_id:
            raise OrderStateError("delivery_waiter_id es requerido para entregar", None, None)
        context.order.delivery_waiter_id = context.actor_id
        if hasattr(context.order, "delivered_at"):
            context.order.delivered_at = datetime.utcnow()

    def _handle_mark_awaiting_payment(self, context: TransitionContext) -> None:
        """Maneja la solicitud de cuenta."""
        if hasattr(context.order, "check_requested_at"):
            context.order.check_requested_at = datetime.utcnow()

    def _handle_pay(self, context: TransitionContext) -> None:
        """Maneja el pago de una orden."""
        payment_method = context.payload.get("payment_method") if context.payload else None
        if not payment_method:
            raise OrderStateError("payment_method es requerido para pagar", None, None)
        context.order.payment_method = payment_method
        if context.payload:
            context.order.payment_reference = context.payload.get("payment_reference")
            if context.payload.get("payment_meta") is not None:
                context.order.payment_meta = context.payload.get("payment_meta")
        if hasattr(context.order, "paid_at"):
            context.order.paid_at = datetime.utcnow()
        if hasattr(context.order, "payment_status"):
            from shared.constants import PaymentStatus

            context.order.payment_status = PaymentStatus.PAID.value

    def _handle_pay_direct(self, context: TransitionContext) -> None:
        """Maneja el pago directo (sin pasar por awaiting_payment)."""
        self._handle_pay(context)

    def _handle_cancel(self, context: TransitionContext) -> None:
        """Maneja la cancelación de una orden."""
        if hasattr(context.order, "payment_status"):
            from shared.constants import PaymentStatus

            context.order.payment_status = PaymentStatus.UNPAID.value
        if context.order.workflow_status in {OrderStatus.NEW.value, OrderStatus.QUEUED.value}:
            context.order.waiter_id = None
            context.order.accepted_at = None
            if hasattr(context.order, "waiter_accepted_at"):
                context.order.waiter_accepted_at = None
            context.order.chef_id = None


# Instancia global de la state machine
order_state_machine = OrderStateMachine()
