"""
Keyboard shortcuts endpoints for clients API.
Allows managing configurable keyboard shortcuts.
"""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify
from sqlalchemy import select

from pronto_shared.db import get_session
from pronto_shared.models import KeyboardShortcut

shortcuts_bp = Blueprint("client_shortcuts", __name__)


@shortcuts_bp.get("/shortcuts")
def get_enabled_shortcuts():
    """Get all enabled keyboard shortcuts for the client app."""
    try:
        with get_session() as db_session:
            stmt = (
                select(KeyboardShortcut)
                .where(KeyboardShortcut.is_enabled)
                .order_by(KeyboardShortcut.sort_order, KeyboardShortcut.category)
            )
            shortcuts = db_session.execute(stmt).scalars().all()

            result = [
                {
                    "id": s.id,
                    "combo": s.combo,
                    "description": s.description,
                    "category": s.category,
                    "callback_function": s.callback_function,
                    "prevent_default": s.prevent_default,
                }
                for s in shortcuts
            ]

            return jsonify({"shortcuts": result}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting shortcuts: {e}", exc_info=True)
        return jsonify({"error": "Error al obtener atajos"}), HTTPStatus.INTERNAL_SERVER_ERROR


@shortcuts_bp.post("/feedback/questions")
def get_feedback_questions():
    """Get all enabled feedback questions for the form."""
    try:
        with get_session() as db_session:
            from pronto_shared.models import FeedbackQuestion

            stmt = (
                select(FeedbackQuestion)
                .where(FeedbackQuestion.is_enabled)
                .order_by(FeedbackQuestion.sort_order)
            )
            questions = db_session.execute(stmt).scalars().all()

            result = [
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

            return jsonify({"questions": result}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting feedback questions: {e}", exc_info=True)
        return jsonify({"error": "Error al obtener preguntas"}), HTTPStatus.INTERNAL_SERVER_ERROR
