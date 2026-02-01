"""Payment gateway wrapper - Facade pattern for payment providers."""

from __future__ import annotations

from shared.models import DiningSession

from .base_provider import PaymentError, PaymentProvider, PaymentResult
from .cash_provider import CashProvider
from .clip_provider import ClipProvider
from .stripe_provider import StripeProvider

# Registry of available payment providers
PAYMENT_PROVIDERS = {
    "stripe": StripeProvider,
    "clip": ClipProvider,
    "cash": CashProvider,
}


def get_payment_provider(provider_name: str) -> PaymentProvider:
    """
    Get a payment provider instance by name.

    Args:
        provider_name: Name of the provider (stripe, clip, cash)

    Returns:
        Payment provider instance

    Raises:
        PaymentError: If provider is not supported
    """
    provider_name = provider_name.lower()

    if provider_name not in PAYMENT_PROVIDERS:
        supported = ", ".join(PAYMENT_PROVIDERS.keys())
        raise PaymentError(
            f"Proveedor de pago '{provider_name}' no soportado. "
            f"Proveedores disponibles: {supported}"
        )

    provider_class = PAYMENT_PROVIDERS[provider_name]
    return provider_class()


def process_payment(
    provider_name: str, session: DiningSession, payment_reference: str | None = None, **kwargs
) -> PaymentResult:
    """
    Process a payment using the specified provider.

    This is the main entry point for payment processing. It uses the Strategy pattern
    to delegate to the appropriate payment provider.

    Args:
        provider_name: Payment provider to use (stripe, clip, cash)
        session: The dining session to charge
        payment_reference: Optional payment reference/method ID
        **kwargs: Provider-specific parameters

    Returns:
        PaymentResult with transaction details

    Raises:
        PaymentError: If payment processing fails

    Example:
        >>> from shared.services.payment_providers import process_payment
        >>> result = process_payment(
        ...     provider_name="stripe",
        ...     session=dining_session,
        ...     payment_reference="pm_1234567890"
        ... )
        >>> print(result.reference)
        'pi_1234567890abcdef'

    Example with Cash:
        >>> result = process_payment(
        ...     provider_name="cash",
        ...     session=dining_session
        ... )
        >>> print(result.reference)
        'cash-123-1699999999'
    """
    provider = get_payment_provider(provider_name)

    return provider.process_payment(session=session, payment_reference=payment_reference, **kwargs)


def validate_provider_configuration(provider_name: str) -> bool:
    """
    Validate that a payment provider is properly configured.

    Args:
        provider_name: Name of the provider to validate

    Returns:
        True if configured correctly

    Raises:
        PaymentError: If configuration is invalid
    """
    provider = get_payment_provider(provider_name)
    return provider.validate_configuration()
