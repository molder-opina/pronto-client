"""
Abstractions for interacting with payment gateways.

DEPRECATED: This module is kept for backward compatibility.
New code should import from shared.services.payment_providers instead:

    from shared.services.payment_providers import process_payment, PaymentError, PaymentResult

The process_payment function now accepts a provider_name parameter:
    result = process_payment("stripe", session, payment_reference="pm_xxx")
    result = process_payment("clip", session)
    result = process_payment("cash", session)
"""

from __future__ import annotations

from shared.models import DiningSession
from shared.services.payment_providers import (
    PaymentError,
    PaymentResult,
)

# Import from new payment_providers module
from shared.services.payment_providers import (
    process_payment as _process_payment,
)

__all__ = ["PaymentError", "PaymentResult", "process_clip_payment", "process_stripe_payment"]


def process_stripe_payment(
    session: DiningSession, payment_method_id: str | None = None
) -> PaymentResult:
    """
    Process a Stripe payment for a dining session.

    DEPRECATED: Use process_payment("stripe", session, payment_reference=...) instead.

    Args:
        session: The dining session to charge
        payment_method_id: Optional Stripe payment method ID for immediate confirmation

    Returns:
        PaymentResult with reference and payment intent details

    Raises:
        PaymentError: If Stripe is not configured or payment fails
    """
    return _process_payment(
        provider_name="stripe", session=session, payment_reference=payment_method_id
    )


def process_clip_payment(
    session: DiningSession, payment_reference: str | None = None
) -> PaymentResult:
    """
    Process a Clip payment for a dining session.

    DEPRECATED: Use process_payment("clip", session, payment_reference=...) instead.

    Args:
        session: The dining session to charge
        payment_reference: Optional Clip transaction reference

    Returns:
        PaymentResult with reference and transaction details

    Raises:
        PaymentError: If Clip is not configured or payment fails
    """
    return _process_payment(
        provider_name="clip", session=session, payment_reference=payment_reference
    )
