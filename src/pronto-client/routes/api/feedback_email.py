"""
Feedback email endpoints for API.
"""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

feedback_email_bp = Blueprint("feedback_email", __name__)


@feedback_email_bp.post("/orders/<int:order_id>/feedback/email-trigger")
def trigger_feedback_email(order_id: int):
    """
    Trigger feedback email after timer expires.
    Called from frontend when feedback prompt times out.

    Validates:
    1) Order exists, is paid and belongs to:
       - authenticated user (registered) OR
       - current anonymous session
    2) No existing feedback_submissions for order_id.
    3) feedback_email_enabled = true.
    4) Determines effective email:
       - registered => user.email
       - anonymous => order/session email
    5) If no effective email => respond 204 (no-op).
    6) Create token (if no active) with TTL hours.
    7) Enqueue/send email and set email_sent_at.

    Important:
    - Idempotent: multiple calls should not send multiple emails (use throttle).
    - Rate limit per order_id.
    """
    from flask import session
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import Order
    from shared.services.feedback_email_service import FeedbackEmailService

    try:
        # Get session from Flask session
        session_id_from_cookie = session.get("dining_session_id")

        # Validate order exists
        with get_session() as db_session:
            order = db_session.execute(
                select(Order).where(Order.id == order_id)
            ).scalar_one_or_none()

            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            # Check if order is paid
            if not FeedbackEmailService._is_order_paid(order):
                return jsonify({"error": "La orden no ha sido pagada"}), HTTPStatus.BAD_REQUEST

            # Validate order belongs to current context
            # Either: registered user OR current anonymous session
            is_valid_context = False
            effective_session_id = None

            if order.customer_id:
                # Registered user - always valid
                is_valid_context = True
                effective_session_id = order.session_id
            elif session_id_from_cookie and session_id_from_cookie == order.session_id:
                # Anonymous user - must be current session
                is_valid_context = True
                effective_session_id = session_id_from_cookie

            if not is_valid_context:
                return jsonify({"error": "No tienes permiso para esta orden"}), HTTPStatus.FORBIDDEN

            # Get timeout from config or request
            timeout_seconds = int(request.args.get("timeout") or 10)

            # Get config values
            from shared.services.business_config_service import ConfigService

            config = ConfigService()
            ttl_hours = config.get_int("feedback_email_token_ttl_hours", 24)

            # Trigger email
            result = FeedbackEmailService.trigger_feedback_email(
                order_id=order_id,
                session_id=effective_session_id,
                timeout_seconds=timeout_seconds,
                ttl_hours=ttl_hours,
            )

            status_code = HTTPStatus.OK if result["success"] else HTTPStatus.INTERNAL_SERVER_ERROR
            return jsonify(result), status_code

    except Exception as e:
        current_app.logger.error(f"Error triggering feedback email: {e}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_email_bp.get("/feedback/email/<token>")
def get_feedback_email_form(token: str):
    """
    Validate token + return questions + context (order_id).

    Token validation rules:
    - Token exists
    - Not expired
    - Not already used

    Returns feedback form context if valid.
    """
    from shared.db import get_session
    from shared.models import FeedbackQuestion
    from shared.services.feedback_email_service import FeedbackEmailService

    try:
        # Validate token
        token_data = FeedbackEmailService.validate_token(token)

        if not token_data:
            return jsonify({"error": "Token inválido o expirado"}), HTTPStatus.BAD_REQUEST

        # Get enabled questions
        with get_session() as db_session:
            questions = (
                db_session.execute(
                    select(FeedbackQuestion)
                    .where(FeedbackQuestion.is_enabled)
                    .order_by(FeedbackQuestion.sort_order)
                )
                .scalars()
                .all()
            )

            questions_data = [
                {
                    "id": q.id,
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "category": q.category,
                    "is_required": q.is_required,
                    "min_rating": q.min_rating,
                    "max_rating": q.max_rating,
                }
                for q in questions
            ]

        # Combine context
        response_data = {**token_data, "questions": questions_data}

        return jsonify(response_data), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting feedback email form: {e}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_email_bp.post("/feedback/email/<token>/submit")
def submit_feedback_email(token: str):
    """
    Submit feedback via email link.

    Validation:
    - Validate token (not expired, not used)
    - Save submission with source="email"
    - Mark token used_at
    - (optional) Mark order/session feedback_completed_at
    """
    from http import HTTPStatus

    from flask import jsonify, request

    from shared.constants import FeedbackCategory
    from shared.db import get_session
    from shared.models import DiningSession, Feedback, Order
    from shared.services.feedback_email_service import FeedbackEmailService

    try:
        # Validate token first
        token_data = FeedbackEmailService.validate_token(token)

        if not token_data:
            return jsonify({"error": "Token inválido o expirado"}), HTTPStatus.BAD_REQUEST

        payload = request.get_json(silent=True) or {}
        ratings = payload.get("ratings", [])
        comment = payload.get("comment", "").strip()

        # Validate ratings
        valid_categories = {cat.value for cat in FeedbackCategory}

        with get_session() as db_session:
            # Fetch order and session
            order = db_session.execute(
                select(Order).where(Order.id == token_data["order_id"])
            ).scalar_one_or_none()

            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            session_obj = db_session.execute(
                select(DiningSession).where(DiningSession.id == token_data["session_id"])
            ).scalar_one_or_none()

            feedback_count = 0

            for rating_data in ratings:
                category = rating_data.get("category")
                rating = rating_data.get("rating")

                if not category or category not in valid_categories:
                    continue

                if not isinstance(rating, int) or rating < 1 or rating > 5:
                    continue

                feedback = Feedback(
                    session_id=token_data["session_id"],
                    customer_id=token_data["user_id"],
                    category=category,
                    rating=rating,
                    comment=comment if category == "overall_experience" else None,
                    is_anonymous=token_data["user_id"] is None,
                )
                db_session.add(feedback)
                feedback_count += 1

            if feedback_count == 0 and comment:
                feedback = Feedback(
                    session_id=token_data["session_id"],
                    customer_id=token_data["user_id"],
                    category=FeedbackCategory.OVERALL_EXPERIENCE.value,
                    rating=3,
                    comment=comment,
                    is_anonymous=token_data["user_id"] is None,
                )
                db_session.add(feedback)
                feedback_count = 1

            # Mark token as used
            FeedbackEmailService.mark_token_used(token_data["token_hash"])

            # Mark session feedback completed
            if session_obj:
                session_obj.feedback_completed_at = datetime.now()
                db_session.flush()

            db_session.commit()

        current_app.logger.info(
            f"Feedback submitted via email for order {token_data['order_id']}: "
            f"{feedback_count} items"
        )

        return jsonify({"success": True, "message": "Gracias por tu feedback"}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error submitting feedback via email: {e}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), HTTPStatus.INTERNAL_SERVER_ERROR
