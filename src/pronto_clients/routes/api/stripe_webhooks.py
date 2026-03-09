"""
Stripe webhook endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: Este workspace no debe asumir un webhook público de Facturapi en `pronto-api`.
      Para Stripe webhooks, se requiere una implementación explícita y compatible
      con guardrails en `pronto-api`; este módulo sigue siendo un proxy técnico temporal.
"""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, request

from pronto_shared.serializers import success_response

stripe_webhooks_bp = Blueprint("client_stripe_webhooks", __name__)


@stripe_webhooks_bp.post("/webhooks/stripe")
def stripe_webhook():
    """PROXY: Stripe webhook handler.

    TEMPORAL: Este es un proxy técnico hasta que pronto-api implemente
    manejo completo de webhooks de Stripe.
    """
    payload = request.get_json(silent=True) or {}

    # For now, just forward to soon-to-be-implemented endpoint
    # In production, this should be implemented directly in pronto-api
    # without going through the client BFF
    result = {
        "message": "Stripe webhook recibido",
        "note": "Este endpoint es un proxy temporal. La implementación completa debe vivir en pronto-api.",
        "forwarded": False,
        "webhook_data": payload,
    }

    return success_response(result), HTTPStatus.OK
