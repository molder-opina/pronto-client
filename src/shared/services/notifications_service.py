"""
Notifications Service for Pronto App
Handles sending transactional notifications (payment confirmation, ticket emails, etc.)
"""

import logging
from collections.abc import Iterable

from shared.db import get_session
from shared.models import DiningSession, Order
from shared.services.email_service import send_ticket_email

logger = logging.getLogger(__name__)


def notify_session_payment(session: DiningSession, channels: Iterable[str] | None = None) -> None:
    """
    Send payment notification to customer (email ticket).

    Args:
        session: The dining session that was paid
        channels: Notification channels (default: ["email"])
    """
    if channels is None:
        channels = ["email"]

    # Generate ticket text
    from shared.services.order_service import generate_ticket

    ticket_text, _ = generate_ticket(session.id)

    # Get effective email from session or orders
    email = _get_effective_email(session)

    if not email or "email" not in channels:
        logger.info(
            "Notificación de pago - email no disponible o no solicitado",
            extra={
                "channels": list(channels),
                "session_id": session.id,
                "has_email": bool(email),
            },
        )
        return

    # Send ticket email
    try:
        restaurant_name = session.customer.name if session.customer else "Cliente"
        sent = send_ticket_email(email, ticket_text, session.id, restaurant_name)

        if sent:
            logger.info(
                f"Ticket enviado exitosamente a {email}",
                extra={"session_id": session.id, "email": email},
            )
        else:
            logger.warning(
                f"No se pudo enviar ticket a {email} (servicio deshabilitado)",
                extra={"session_id": session.id, "email": email},
            )
    except Exception as exc:
        logger.error(
            f"Error enviando ticket email: {exc}",
            extra={"session_id": session.id, "email": email},
            exc_info=True,
        )


def _get_effective_email(session: DiningSession) -> str | None:
    """
    Get the effective email for a session.

    Priority:
    1. Session customer.email (if not temporary)
    2. Order customer_email (if not temporary)
    3. None

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


def send_order_confirmation_email(order_id: int) -> bool:
    """
    Send order confirmation email to customer.

    Args:
        order_id: Order ID

    Returns:
        True if sent successfully
    """
    with get_session() as session:
        from sqlalchemy.orm import joinedload

        order = (
            session.execute(
                select(Order)
                .options(
                    joinedload(Order.customer),
                    joinedload(Order.dining_session),
                )
                .where(Order.id == order_id)
            )
            .unique()
            .scalars()
            .one_or_none()
        )

        if not order:
            logger.warning(f"Orden {order_id} no encontrada para enviar confirmación")
            return False

        email = _get_effective_email(order.dining_session) if order.dining_session else None

        if not email:
            logger.info(f"Orden {order_id} sin email válido para confirmación")
            return False

        try:
            subject = f"Tu pedido #{order_id} - Pronto Cafetería"
            body_text = f"""
Tu pedido ha sido recibido exitosamente!

Número de pedido: #{order_id}
Mesa: {order.dining_session.table_number if order.dining_session else "N/A"}

Los detalles de tu pedido están disponibles en nuestra aplicación.

Gracias por tu preferencia.
"""
            from shared.services.email_service import email_service

            sent = email_service.send_email(email, subject, body_text)

            if sent:
                logger.info(f"Email de confirmación enviado a {email} para orden #{order_id}")
            return sent

        except Exception as exc:
            logger.error(
                f"Error enviando email de confirmación: {exc}",
                extra={"order_id": order_id, "email": email},
                exc_info=True,
            )
            return False
