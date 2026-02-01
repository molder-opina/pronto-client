"""Clip payment provider implementation."""

from __future__ import annotations

import os
from decimal import Decimal

from shared.models import DiningSession

from .base_provider import PaymentError, PaymentProvider, PaymentResult


class ClipProvider(PaymentProvider):
    """Clip payment gateway provider (Mexico)."""

    def validate_configuration(self) -> bool:
        """Validate Clip configuration.

        Returns True if sandbox mode is enabled or API key is configured.
        """
        # Allow sandbox mode without API key
        sandbox_mode = os.getenv("CLIP_SANDBOX_MODE", "false").lower() == "true"
        api_key = os.getenv("CLIP_API_KEY")

        if not api_key and not sandbox_mode:
            raise PaymentError(
                "Clip no está configurado. Configure CLIP_API_KEY o active CLIP_SANDBOX_MODE."
            )
        return True

    def process_payment(
        self, session: DiningSession, payment_reference: str | None = None, **kwargs
    ) -> PaymentResult:
        """
        Process a Clip payment for a dining session.

        Args:
            session: The dining session to charge
            payment_reference: Optional Clip transaction reference
            **kwargs: Additional Clip parameters

        Returns:
            PaymentResult with Clip transaction details

        Raises:
            PaymentError: If Clip is not configured or payment fails
        """
        self.validate_configuration()

        api_key = os.getenv("CLIP_API_KEY")
        sandbox_mode = os.getenv("CLIP_SANDBOX_MODE", "false").lower() == "true"
        clip_api_url = os.getenv("CLIP_API_URL", "https://api-gw.payclip.com")

        # Convert amount to cents
        amount_cents = self._convert_to_cents(Decimal(session.total_amount))

        if amount_cents <= 0:
            raise PaymentError("El monto a pagar debe ser mayor a 0")

        # Sandbox mode: simulate successful payment without API call
        if sandbox_mode or not api_key:
            import time

            transaction_id = payment_reference or f"clip-sandbox-{session.id}-{int(time.time())}"
            return PaymentResult(
                reference=transaction_id, transaction_id=transaction_id, provider="clip"
            )

        try:
            import requests
        except ImportError:
            raise PaymentError("Requests no está instalado. Ejecute: pip install requests")

        try:
            # Make API call to Clip
            response = requests.post(
                f"{clip_api_url}/charge",
                json={
                    "amount": amount_cents,
                    "currency": "MXN",
                    "description": f"Cuenta #{session.id} - Mesa {session.table_number or 'N/A'}",
                    "metadata": {
                        "session_id": session.id,
                        "table_number": session.table_number or "",
                        "customer_name": session.customer.name if session.customer else "",
                    },
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                transaction_id = data.get("id") or payment_reference or f"clip-{session.id}"

                return PaymentResult(
                    reference=transaction_id, transaction_id=transaction_id, provider="clip"
                )
            else:
                try:
                    error_msg = response.json().get("message", "Error desconocido")
                except Exception:
                    error_msg = f"HTTP {response.status_code}"
                raise PaymentError(f"Error de Clip: {error_msg}")

        except requests.exceptions.Timeout:
            raise PaymentError("Timeout al conectar con Clip. Intente nuevamente.")
        except requests.exceptions.ConnectionError:
            raise PaymentError("No se pudo conectar con el servidor de Clip.")
        except requests.exceptions.RequestException as e:
            raise PaymentError(f"Error de conexión con Clip: {e!s}")
        except Exception as e:
            raise PaymentError(f"Error inesperado: {e!s}")
