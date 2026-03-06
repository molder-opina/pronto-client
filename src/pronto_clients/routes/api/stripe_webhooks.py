"""
Stripe webhook endpoint for handling asynchronous payment events.
"""
from __future__ import annotations

import os
from http import HTTPStatus

from flask import Blueprint, request, Response

try:
    import stripe
    from stripe.error import SignatureVerificationError
except ModuleNotFoundError:  # pragma: no cover - env without stripe sdk
    stripe = None

    class SignatureVerificationError(Exception):
        pass

from pronto_shared.trazabilidad import get_logger
from pronto_shared.services.order_service import finalize_payment
from pronto_shared.db import get_session
from pronto_shared.models import DiningSession

logger = get_logger(__name__)

stripe_webhooks_bp = Blueprint("stripe_webhooks", __name__)

# It's critical to secure this endpoint.
# Get secrets from environment variables.
STRIPE_API_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if stripe is not None:
    stripe.api_key = STRIPE_API_KEY


@stripe_webhooks_bp.post("/webhooks/stripe")
def stripe_webhook():
    """
    Handles incoming webhooks from Stripe.
    """
    if stripe is None:
        logger.error("Stripe SDK is not installed in this environment.")
        return "Stripe SDK not available", HTTPStatus.SERVICE_UNAVAILABLE

    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured.")
        return "Configuration error", HTTPStatus.INTERNAL_SERVER_ERROR

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        logger.warning(f"Invalid webhook payload: {e}")
        return "Invalid payload", HTTPStatus.BAD_REQUEST
    except SignatureVerificationError as e:
        # Invalid signature
        logger.warning(f"Invalid webhook signature: {e}")
        return "Invalid signature", HTTPStatus.BAD_REQUEST

    # Handle the event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        session_id = payment_intent["metadata"].get("dining_session_id")
        
        if not session_id:
            logger.error("Webhook received for payment_intent without a dining_session_id.")
            return "Missing dining_session_id in metadata", HTTPStatus.BAD_REQUEST

        logger.info(f"PaymentIntent succeeded for session {session_id}.")

        # Check if the session is already paid
        with get_session() as db:
            session = db.get(DiningSession, session_id)
            if session and session.status == 'paid':
                logger.info(f"Session {session_id} is already marked as paid. Ignoring webhook.")
                return "Session already paid", HTTPStatus.OK
        
        # Call the finalize_payment service
        data, status = finalize_payment(
            session_id=session_id,
            payment_method="stripe",
            payment_reference=payment_intent["id"],
        )

        if status != HTTPStatus.OK:
            logger.error(f"Failed to finalize payment for session {session_id}: {data.get('error')}")
            # Here you might want to enqueue a retry or send an alert
            return "Failed to finalize payment", HTTPStatus.INTERNAL_SERVER_ERROR

        logger.info(f"Successfully finalized payment for session {session_id}.")

    else:
        logger.info(f"Received unhandled event type {event['type']}")

    return "Success", HTTPStatus.OK
