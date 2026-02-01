"""
Stripe and Clip payment endpoints for clients API.
"""

from decimal import Decimal
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from shared.supabase.realtime import emit_waiter_call

stripe_payments_bp = Blueprint("client_stripe_payments", __name__)


@stripe_payments_bp.post("/sessions/<int:session_id>/pay/stripe")
def pay_with_stripe(session_id: int):
    """Process payment with Stripe for a dining session."""
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import DiningSession
    from shared.services.payment_providers.stripe_provider import PaymentError, StripeProvider

    payload = request.get_json(silent=True) or {}
    tip_amount = payload.get("tip_amount")
    tip_percentage = payload.get("tip_percentage")

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            if dining_session.status == "paid":
                return jsonify({"error": "Esta sesión ya está pagada"}), HTTPStatus.BAD_REQUEST

            if tip_amount is not None:
                dining_session.tip_amount = Decimal(str(tip_amount))
            elif tip_percentage is not None:
                subtotal = Decimal(str(dining_session.subtotal))
                dining_session.tip_amount = subtotal * Decimal(str(tip_percentage)) / Decimal("100")

            dining_session.recompute_totals()
            db_session.commit()
            db_session.refresh(dining_session)

            stripe_provider = StripeProvider()
            result = stripe_provider.process_payment(dining_session)

            return jsonify(
                {
                    "client_secret": result.client_secret,
                    "payment_intent_id": result.payment_intent_id,
                    "total_amount": float(dining_session.total_amount),
                    "subtotal": float(dining_session.subtotal),
                    "tax_amount": float(dining_session.tax_amount or 0),
                    "tip_amount": float(dining_session.tip_amount or 0),
                }
            ), HTTPStatus.OK

    except PaymentError as e:
        current_app.logger.error(f"Stripe payment error: {e}")
        return jsonify({"error": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error processing Stripe payment: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al procesar pago con Stripe"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@stripe_payments_bp.post("/sessions/<int:session_id>/pay/clip")
def pay_with_clip(session_id: int):
    """Register a Clip/Terminal payment request for a dining session."""
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import DiningSession, Notification, WaiterCall

    payload = request.get_json(silent=True) or {}
    tip_amount = payload.get("tip_amount")
    tip_percentage = payload.get("tip_percentage")

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            if dining_session.status == "paid":
                return jsonify({"error": "Esta sesión ya está pagada"}), HTTPStatus.BAD_REQUEST

            if tip_amount is not None:
                dining_session.tip_amount = Decimal(str(tip_amount))
            elif tip_percentage is not None:
                subtotal = Decimal(str(dining_session.subtotal))
                dining_session.tip_amount = subtotal * Decimal(str(tip_percentage)) / Decimal("100")

            dining_session.recompute_totals()

            dining_session.status = "awaiting_payment"
            dining_session.payment_method = "clip"

            table_number = dining_session.table_number or "N/A"
            waiter_call = WaiterCall(
                session_id=session_id,
                table_number=table_number,
                status="pending",
                notes="payment_request:clip",
            )
            db_session.add(waiter_call)
            db_session.flush()

            notification = Notification(
                notification_type="payment_request",
                recipient_type="all_waiters",
                recipient_id=None,
                title=f"Pago con Terminal - Mesa {table_number}",
                message=f"Cliente solicita pagar ${dining_session.total_amount:.2f} con terminal Clip",
                data=f'{{"table_number": "{table_number}", "session_id": {session_id}, "waiter_call_id": {waiter_call.id}, "payment_method": "clip", "amount": {float(dining_session.total_amount)}}}',
                priority="high",
            )
            db_session.add(notification)
            db_session.commit()

            call_id = waiter_call.id

            emit_waiter_call(
                call_id=call_id,
                session_id=session_id,
                table_number=table_number,
                status="pending",
                call_type="payment_request:clip",
                order_numbers=[],
                waiter_id=None,
                waiter_name=None,
                created_at=waiter_call.created_at,
            )

            current_app.logger.info(
                f"Clip payment requested for session {session_id}, total={dining_session.total_amount}"
            )

            return jsonify(
                {
                    "success": True,
                    "message": "Solicitud de pago con terminal enviada. Un mesero vendrá a procesar tu pago.",
                    "waiter_call_id": call_id,
                    "total_amount": float(dining_session.total_amount),
                    "subtotal": float(dining_session.subtotal),
                    "tax_amount": float(dining_session.tax_amount or 0),
                    "tip_amount": float(dining_session.tip_amount or 0),
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error processing Clip payment request: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al procesar solicitud de pago"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
