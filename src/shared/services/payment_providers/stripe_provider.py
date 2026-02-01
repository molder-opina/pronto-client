"""Stripe payment provider implementation."""

from __future__ import annotations

import os
from decimal import Decimal

from shared.models import DiningSession

from .base_provider import PaymentError, PaymentProvider, PaymentResult


class StripeProvider(PaymentProvider):
    """Stripe payment gateway provider."""

    def validate_configuration(self) -> bool:
        """Validate Stripe configuration."""
        api_key = os.getenv("STRIPE_API_KEY")
        if not api_key:
            raise PaymentError("Stripe no está configurado. Configure STRIPE_API_KEY.")
        return True

    def process_payment(
        self, session: DiningSession, payment_reference: str | None = None, **kwargs
    ) -> PaymentResult:
        """
        Process a Stripe payment for a dining session.

        Args:
            session: The dining session to charge
            payment_reference: Optional Stripe payment method ID
            **kwargs: Additional Stripe parameters

        Returns:
            PaymentResult with Stripe payment intent details

        Raises:
            PaymentError: If Stripe is not configured or payment fails
        """
        self.validate_configuration()

        try:
            import stripe
        except ImportError:
            raise PaymentError("Stripe SDK no está instalado. Ejecute: pip install stripe")

        api_key = os.getenv("STRIPE_API_KEY")
        stripe.api_key = api_key

        # Convert amount to cents
        amount_cents = self._convert_to_cents(Decimal(session.total_amount))

        if amount_cents <= 0:
            raise PaymentError("El monto a pagar debe ser mayor a 0")

        # Get currency from environment or default to MXN (Mexican Peso)
        currency = os.getenv("STRIPE_CURRENCY", "mxn").lower()

        try:
            # Create a PaymentIntent
            payment_intent_kwargs = {
                "amount": amount_cents,
                "currency": currency,
                "description": f"Cuenta #{session.id} - Mesa {session.table_number or 'N/A'}",
                "metadata": {
                    "session_id": session.id,
                    "table_number": session.table_number or "",
                    "customer_name": session.customer.name if session.customer else "",
                },
            }

            # Add payment method if provided
            if payment_reference:
                payment_intent_kwargs["payment_method"] = payment_reference
                payment_intent_kwargs["confirm"] = True
            else:
                payment_intent_kwargs["automatic_payment_methods"] = {"enabled": True}

            payment_intent = stripe.PaymentIntent.create(**payment_intent_kwargs)

            return PaymentResult(
                reference=payment_intent.id,
                payment_intent_id=payment_intent.id,
                client_secret=payment_intent.client_secret,
                provider="stripe",
            )

        except stripe.error.CardError as e:
            raise PaymentError(f"Tarjeta rechazada: {e.user_message}")
        except stripe.error.InvalidRequestError as e:
            raise PaymentError(f"Solicitud inválida: {e!s}")
        except stripe.error.AuthenticationError:
            raise PaymentError("Error de autenticación con Stripe. Verifique API key.")
        except stripe.error.StripeError as e:
            raise PaymentError(f"Error de Stripe: {e!s}")
        except Exception as e:
            raise PaymentError(f"Error inesperado: {e!s}")
