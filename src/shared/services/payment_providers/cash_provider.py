"""Cash payment provider implementation."""

from __future__ import annotations

from datetime import datetime

from shared.models import DiningSession

from .base_provider import PaymentError, PaymentProvider, PaymentResult


class CashProvider(PaymentProvider):
    """Cash payment provider (no external gateway needed)."""

    def validate_configuration(self) -> bool:
        """Cash doesn't require configuration."""
        return True

    def process_payment(
        self, session: DiningSession, payment_reference: str | None = None, **kwargs
    ) -> PaymentResult:
        """
        Process a cash payment for a dining session.

        Args:
            session: The dining session to charge
            payment_reference: Optional custom reference
            **kwargs: Additional parameters (unused)

        Returns:
            PaymentResult with cash transaction reference

        Raises:
            PaymentError: If amount is invalid
        """
        if session.total_amount <= 0:
            raise PaymentError("El monto a pagar debe ser mayor a 0")

        # Generate reference if not provided
        if not payment_reference:
            timestamp = int(datetime.utcnow().timestamp())
            payment_reference = f"cash-{session.id}-{timestamp}"

        return PaymentResult(reference=payment_reference, provider="cash")
