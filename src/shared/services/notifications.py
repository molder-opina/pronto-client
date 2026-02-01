"""Utility helpers to send transactional notifications."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from shared.models import DiningSession

logger = logging.getLogger(__name__)


def notify_session_payment(session: DiningSession, channels: Iterable[str] | None = None) -> None:
    """
    Placeholder notification dispatcher. In a real deployment this should
    integrate with SMS, WhatsApp or email providers.
    """
    payload = {
        "session_id": session.id,
        "customer": session.customer.email or session.customer.phone,
        "total": float(session.total_amount),
        "payment_method": session.payment_method,
        "reference": session.payment_reference,
    }
    chosen_channels = list(channels) if channels else ["email"]
    logger.info(
        "Notificación de pago enviada", extra={"channels": chosen_channels, "payload": payload}
    )
