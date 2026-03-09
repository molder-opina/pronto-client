"""
Stripe webhook endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: This module implements business logic that should live in pronto-api.
# Sunset date: TBD (to be defined in roadmap)
# Reason: pronto-client should not implement business endpoints per AGENTS.md section 12.4.2.
# Single API authority: pronto-api at :6082 under "/api/*".
# Migration plan: Migrate business logic to pronto-api
# Reference: AGENTS.md section 12.4.2, 12.4.3, 12.4.4

NOTE: This workspace should not assume a public Facturapi webhook in `pronto-api`.
       For Stripe webhooks, explicit implementation compatible with
       guardrails in `pronto-api` is required; this module remains a technical proxy.
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
