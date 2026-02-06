"""
Feedback endpoints for clients API.
"""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

feedback_bp = Blueprint("client_feedback", __name__)


@feedback_bp.post("/sessions/<int:session_id>/feedback")
def submit_session_feedback(session_id: int):
    """Submit customer feedback for a dining session."""
    from sqlalchemy import select

    from pronto_shared.constants import FeedbackCategory
    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Feedback

    payload = request.get_json(silent=True) or {}
    ratings = payload.get("ratings") or []
    comment = payload.get("comment", "").strip()

    valid_categories = {cat.value for cat in FeedbackCategory}

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            customer_id = None
            if dining_session.orders:
                for order in dining_session.orders:
                    if order.customer_id:
                        customer_id = order.customer_id
                        break

            feedback_count = 0

            for rating_data in ratings:
                category = rating_data.get("category")
                rating = rating_data.get("rating")

                if not category or category not in valid_categories:
                    continue

                if not isinstance(rating, int) or rating < 1 or rating > 5:
                    continue

                feedback = Feedback(
                    session_id=session_id,
                    customer_id=customer_id,
                    category=category,
                    rating=rating,
                    comment=comment if category == "overall_experience" else None,
                    is_anonymous=customer_id is None,
                )
                db_session.add(feedback)
                feedback_count += 1

            if feedback_count == 0 and comment:
                feedback = Feedback(
                    session_id=session_id,
                    customer_id=customer_id,
                    category=FeedbackCategory.OVERALL_EXPERIENCE.value,
                    rating=3,
                    comment=comment,
                    is_anonymous=customer_id is None,
                )
                db_session.add(feedback)
                feedback_count = 1

            db_session.commit()

            current_app.logger.info(
                f"Feedback submitted for session {session_id}: {feedback_count} items"
            )

            return jsonify(
                {
                    "success": True,
                    "message": "Gracias por tu feedback",
                    "feedback_count": feedback_count,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error submitting feedback: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al enviar feedback"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.post("/feedback/bulk")
def submit_feedback_bulk():
    """Submit multiple feedback items in a single request."""
    from sqlalchemy import select

    from pronto_shared.constants import FeedbackCategory
    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Feedback

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    employee_id = payload.get("employee_id")
    feedback_items = payload.get("feedback_items", [])
    is_anonymous = payload.get("is_anonymous", False)

    if not session_id:
        return jsonify({"error": "session_id es requerido"}), HTTPStatus.BAD_REQUEST

    if not feedback_items or not isinstance(feedback_items, list):
        return jsonify(
            {"error": "feedback_items debe ser una lista no vacía"}
        ), HTTPStatus.BAD_REQUEST

    valid_categories = {cat.value for cat in FeedbackCategory}

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            customer_id = None
            if not is_anonymous and dining_session.orders:
                for order in dining_session.orders:
                    if order.customer_id:
                        customer_id = order.customer_id
                        break

            feedback_count = 0

            for item in feedback_items:
                category = item.get("category")
                rating = item.get("rating")

                if not category or category not in valid_categories:
                    continue

                if not isinstance(rating, int) or rating < 1 or rating > 5:
                    continue

                feedback = Feedback(
                    session_id=session_id,
                    customer_id=customer_id,
                    employee_id=employee_id,
                    category=category,
                    rating=rating,
                    comment=item.get("comment"),
                    is_anonymous=is_anonymous,
                )
                db_session.add(feedback)
                feedback_count += 1

            db_session.commit()

            current_app.logger.info(
                f"Bulk feedback submitted for session {session_id}: {feedback_count} items"
            )

            return jsonify(
                {
                    "success": True,
                    "message": "Gracias por tu feedback",
                    "feedback_count": feedback_count,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error submitting bulk feedback: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al enviar feedback"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
