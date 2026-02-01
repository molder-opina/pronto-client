"""Base payment provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from shared.models import DiningSession


class PaymentError(Exception):
    """Raised when a payment gateway call fails."""


@dataclass
class PaymentResult:
    """Result of a payment transaction."""

    reference: str
    payment_intent_id: str | None = None
    client_secret: str | None = None
    transaction_id: str | None = None
    provider: str | None = None


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""

    @abstractmethod
    def process_payment(
        self, session: DiningSession, payment_reference: str | None = None, **kwargs
    ) -> PaymentResult:
        """
        Process a payment for a dining session.

        Args:
            session: The dining session to charge
            payment_reference: Optional payment reference/method ID
            **kwargs: Provider-specific parameters

        Returns:
            PaymentResult with transaction details

        Raises:
            PaymentError: If payment processing fails
        """
        pass

    @abstractmethod
    def validate_configuration(self) -> bool:
        """
        Validate that the provider is properly configured.

        Returns:
            True if configured, raises PaymentError otherwise

        Raises:
            PaymentError: If configuration is invalid
        """
        pass

    def _convert_to_cents(self, amount: Decimal) -> int:
        """Convert decimal amount to cents."""
        from decimal import ROUND_HALF_UP

        return int(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
