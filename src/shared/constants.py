"""
Application constants and enums.
"""

from enum import Enum


class OrderStatus(str, Enum):
    NEW = "new"
    QUEUED = "queued"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    AWAITING_TIP = "awaiting_tip"
    PAID = "paid"


class SessionStatus(str, Enum):
    OPEN = "open"
    AWAITING_TIP = "awaiting_tip"
    AWAITING_PAYMENT = "awaiting_payment"
    AWAITING_PAYMENT_CONFIRMATION = "awaiting_payment_confirmation"
    CLOSED = "closed"
    PAID = "paid"


class Roles(str, Enum):
    SYSTEM = "system"
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    WAITER = "waiter"
    CHEF = "chef"
    CASHIER = "cashier"
    CONTENT_MANAGER = "content_manager"
    STAFF = "staff"

    @classmethod
    def is_admin(cls, role: str) -> bool:
        return role in {cls.SYSTEM, cls.SUPER_ADMIN, cls.ADMIN}

    @classmethod
    def all_values(cls) -> set:
        return {member.value for member in cls}


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    STRIPE = "stripe"
    CLIP = "clip"


class ModificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ModificationInitiator(str, Enum):
    CUSTOMER = "customer"
    WAITER = "waiter"


class FeedbackCategory(str, Enum):
    """Categories for feedback ratings."""

    WAITER_SERVICE = "waiter_service"
    FOOD_QUALITY = "food_quality"
    FOOD_PRESENTATION = "food_presentation"
    OVERALL_EXPERIENCE = "overall_experience"


OPEN_ORDER_STATUSES = {
    OrderStatus.NEW,
    OrderStatus.QUEUED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.DELIVERED,
    OrderStatus.AWAITING_PAYMENT,
}

NON_CANCELABLE_STATUSES = {
    OrderStatus.PAID,
    OrderStatus.CANCELLED,
}

CLIENT_CANCELABLE_STATUSES = {
    OrderStatus.NEW,
    OrderStatus.QUEUED,
}

ORDER_TRANSITIONS = {
    (OrderStatus.NEW, OrderStatus.QUEUED): {
        "action": "accept_or_queue",
        "allowed_scopes": {"waiter", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.NEW, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"client", "waiter", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.QUEUED, OrderStatus.PREPARING): {
        "action": "kitchen_start",
        "allowed_scopes": {"chef", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.QUEUED, OrderStatus.READY): {
        "action": "skip_kitchen",
        "allowed_scopes": {"system"},
        "requires_justification": False,
    },
    (OrderStatus.QUEUED, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"client", "waiter", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.PREPARING, OrderStatus.READY): {
        "action": "kitchen_complete",
        "allowed_scopes": {"chef", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.PREPARING, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"waiter", "admin", "system"},
        "requires_justification": True,
    },
    (OrderStatus.READY, OrderStatus.DELIVERED): {
        "action": "deliver",
        "allowed_scopes": {"waiter", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.READY, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"admin", "system"},
        "requires_justification": True,
    },
    (OrderStatus.DELIVERED, OrderStatus.AWAITING_PAYMENT): {
        "action": "mark_awaiting_payment",
        "allowed_scopes": {"cashier", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.DELIVERED, OrderStatus.PAID): {
        "action": "pay_direct",
        "allowed_scopes": {"admin", "system"},
        "requires_justification": True,
    },
    (OrderStatus.DELIVERED, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"admin", "system"},
        "requires_justification": True,
    },
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID): {
        "action": "pay",
        "allowed_scopes": {"cashier", "admin", "system"},
        "requires_justification": False,
    },
    (OrderStatus.AWAITING_PAYMENT, OrderStatus.CANCELLED): {
        "action": "cancel",
        "allowed_scopes": {"admin", "system"},
        "requires_justification": True,
    },
}


ORDER_STATUS_META_DEFAULT = {
    OrderStatus.NEW.value: {
        "client_label": "Orden creada",
        "employee_label": "Esperando mesero",
        "admin_desc": "Orden creada; aún no ha sido enviada a preparación.",
    },
    OrderStatus.QUEUED.value: {
        "client_label": "En proceso",
        "employee_label": "Enviando a cocina",
        "admin_desc": "Orden confirmada y en cola para preparación o salto de cocina.",
    },
    OrderStatus.PREPARING.value: {
        "client_label": "Preparando tu orden",
        "employee_label": "En cocina",
        "admin_desc": "Preparación en curso (cocina inició).",
    },
    OrderStatus.READY.value: {
        "client_label": "Lista",
        "employee_label": "Listo entrega",
        "admin_desc": "Preparación finalizada; lista para entrega.",
    },
    OrderStatus.DELIVERED.value: {
        "client_label": "Entregada",
        "employee_label": "Entregado",
        "admin_desc": "Orden entregada al cliente.",
    },
    OrderStatus.AWAITING_PAYMENT.value: {
        "client_label": "Pendiente de pago",
        "employee_label": "Esperando pago",
        "admin_desc": "Orden entregada; esperando cobro/registro.",
    },
    OrderStatus.PAID.value: {
        "client_label": "Pagada",
        "employee_label": "Pagada",
        "admin_desc": "Pago registrado y confirmado.",
    },
    OrderStatus.CANCELLED.value: {
        "client_label": "Cancelada",
        "employee_label": "Cancelada",
        "admin_desc": "Orden cancelada.",
    },
}

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
