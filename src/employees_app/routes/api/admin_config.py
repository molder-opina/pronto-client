"""
Admin endpoints for managing keyboard shortcuts and feedback questions.
"""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import delete, select

from shared.db import get_session
from shared.models import FeedbackQuestion, KeyboardShortcut

admin_config_bp = Blueprint("admin_config", __name__)


# ============ KEYBOARD SHORTCUTS ============


@admin_config_bp.get("/shortcuts")
def get_all_shortcuts():
    """Get all keyboard shortcuts (including disabled)."""
    try:
        with get_session() as db_session:
            stmt = select(KeyboardShortcut).order_by(
                KeyboardShortcut.sort_order, KeyboardShortcut.category
            )
            shortcuts = db_session.execute(stmt).scalars().all()

            result = [
                {
                    "id": s.id,
                    "combo": s.combo,
                    "description": s.description,
                    "category": s.category,
                    "callback_function": s.callback_function,
                    "is_enabled": s.is_enabled,
                    "prevent_default": s.prevent_default,
                    "sort_order": s.sort_order,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in shortcuts
            ]

            return jsonify({"shortcuts": result}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting shortcuts: {e}", exc_info=True)
        return jsonify({"error": "Error al obtener atajos"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.post("/shortcuts")
def create_shortcut():
    """Create a new keyboard shortcut."""
    try:
        payload = request.get_json(silent=True) or {}
        combo = payload.get("combo", "").strip()
        description = payload.get("description", "").strip()
        category = payload.get("category", "General").strip()
        callback_function = payload.get("callback_function", "").strip()

        if not combo or not description or not callback_function:
            return jsonify(
                {"error": "Combo, descripción y función son requeridos"}
            ), HTTPStatus.BAD_REQUEST

        with get_session() as db_session:
            # Check if combo already exists
            existing = db_session.execute(
                select(KeyboardShortcut).where(KeyboardShortcut.combo == combo)
            ).scalar_one_or_none()

            if existing:
                return jsonify({"error": "Este combo ya existe"}), HTTPStatus.CONFLICT

            shortcut = KeyboardShortcut(
                combo=combo,
                description=description,
                category=category,
                callback_function=callback_function,
                is_enabled=payload.get("is_enabled", True),
                prevent_default=payload.get("prevent_default", False),
                sort_order=payload.get("sort_order", 0),
            )
            db_session.add(shortcut)
            db_session.commit()

            return jsonify(
                {
                    "success": True,
                    "shortcut": {
                        "id": shortcut.id,
                        "combo": shortcut.combo,
                        "description": shortcut.description,
                    },
                }
            ), HTTPStatus.CREATED

    except Exception as e:
        current_app.logger.error(f"Error creating shortcut: {e}", exc_info=True)
        return jsonify({"error": "Error al crear atajo"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.put("/shortcuts/<int:shortcut_id>")
def update_shortcut(shortcut_id: int):
    """Update a keyboard shortcut."""
    try:
        payload = request.get_json(silent=True) or {}

        with get_session() as db_session:
            shortcut = db_session.execute(
                select(KeyboardShortcut).where(KeyboardShortcut.id == shortcut_id)
            ).scalar_one_or_none()

            if not shortcut:
                return jsonify({"error": "Atajo no encontrado"}), HTTPStatus.NOT_FOUND

            # Update fields
            if "description" in payload:
                shortcut.description = payload["description"].strip()
            if "category" in payload:
                shortcut.category = payload["category"].strip()
            if "callback_function" in payload:
                shortcut.callback_function = payload["callback_function"].strip()
            if "is_enabled" in payload:
                shortcut.is_enabled = bool(payload["is_enabled"])
            if "prevent_default" in payload:
                shortcut.prevent_default = bool(payload["prevent_default"])
            if "sort_order" in payload:
                shortcut.sort_order = int(payload["sort_order"])

            db_session.commit()

            return jsonify({"success": True}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error updating shortcut: {e}", exc_info=True)
        return jsonify({"error": "Error al actualizar atajo"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.delete("/shortcuts/<int:shortcut_id>")
def delete_shortcut(shortcut_id: int):
    """Delete a keyboard shortcut."""
    try:
        with get_session() as db_session:
            db_session.execute(delete(KeyboardShortcut).where(KeyboardShortcut.id == shortcut_id))
            db_session.commit()

            return jsonify({"success": True}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error deleting shortcut: {e}", exc_info=True)
        return jsonify({"error": "Error al eliminar atajo"}), HTTPStatus.INTERNAL_SERVER_ERROR


# ============ FEEDBACK QUESTIONS ============


@admin_config_bp.get("/feedback/questions")
def get_all_questions():
    """Get all feedback questions (including disabled)."""
    try:
        with get_session() as db_session:
            stmt = select(FeedbackQuestion).order_by(FeedbackQuestion.sort_order)
            questions = db_session.execute(stmt).scalars().all()

            result = [
                {
                    "id": q.id,
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "category": q.category,
                    "is_required": q.is_required,
                    "is_enabled": q.is_enabled,
                    "sort_order": q.sort_order,
                    "min_rating": q.min_rating,
                    "max_rating": q.max_rating,
                    "created_at": q.created_at.isoformat() if q.created_at else None,
                    "updated_at": q.updated_at.isoformat() if q.updated_at else None,
                }
                for q in questions
            ]

            return jsonify({"questions": result}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting questions: {e}", exc_info=True)
        return jsonify({"error": "Error al obtener preguntas"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.post("/feedback/questions")
def create_question():
    """Create a new feedback question."""
    try:
        payload = request.get_json(silent=True) or {}
        question_text = payload.get("question_text", "").strip()

        if not question_text:
            return jsonify({"error": "La pregunta es requerida"}), HTTPStatus.BAD_REQUEST

        with get_session() as db_session:
            question = FeedbackQuestion(
                question_text=question_text,
                question_type=payload.get("question_type", "rating"),
                category=payload.get("category"),
                is_required=payload.get("is_required", True),
                is_enabled=payload.get("is_enabled", True),
                sort_order=payload.get("sort_order", 0),
                min_rating=payload.get("min_rating", 1),
                max_rating=payload.get("max_rating", 5),
            )
            db_session.add(question)
            db_session.commit()

            return jsonify(
                {
                    "success": True,
                    "question": {
                        "id": question.id,
                        "question_text": question.question_text,
                    },
                }
            ), HTTPStatus.CREATED

    except Exception as e:
        current_app.logger.error(f"Error creating question: {e}", exc_info=True)
        return jsonify({"error": "Error al crear pregunta"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.put("/feedback/questions/<int:question_id>")
def update_question(question_id: int):
    """Update a feedback question."""
    try:
        payload = request.get_json(silent=True) or {}

        with get_session() as db_session:
            question = db_session.execute(
                select(FeedbackQuestion).where(FeedbackQuestion.id == question_id)
            ).scalar_one_or_none()

            if not question:
                return jsonify({"error": "Pregunta no encontrada"}), HTTPStatus.NOT_FOUND

            # Update fields
            if "question_text" in payload:
                question.question_text = payload["question_text"].strip()
            if "question_type" in payload:
                question.question_type = payload["question_type"]
            if "category" in payload:
                question.category = payload["category"]
            if "is_required" in payload:
                question.is_required = bool(payload["is_required"])
            if "is_enabled" in payload:
                question.is_enabled = bool(payload["is_enabled"])
            if "sort_order" in payload:
                question.sort_order = int(payload["sort_order"])
            if "min_rating" in payload:
                question.min_rating = int(payload["min_rating"])
            if "max_rating" in payload:
                question.max_rating = int(payload["max_rating"])

            db_session.commit()

            return jsonify({"success": True}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error updating question: {e}", exc_info=True)
        return jsonify({"error": "Error al actualizar pregunta"}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.delete("/feedback/questions/<int:question_id>")
def delete_question(question_id: int):
    """Delete a feedback question."""
    try:
        with get_session() as db_session:
            db_session.execute(delete(FeedbackQuestion).where(FeedbackQuestion.id == question_id))
            db_session.commit()

            return jsonify({"success": True}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error deleting question: {e}", exc_info=True)
        return jsonify({"error": "Error al eliminar pregunta"}), HTTPStatus.INTERNAL_SERVER_ERROR


# ============ FEEDBACK SETTINGS ============


@admin_config_bp.get("/settings/feedback")
def get_feedback_settings():
    """Get all feedback-related settings."""
    from shared.models import SystemSetting

    try:
        with get_session() as db_session:
            settings_keys = [
                "feedback_prompt_enabled",
                "feedback_prompt_timeout_seconds",
                "feedback_email_enabled",
                "feedback_email_token_ttl_hours",
                "feedback_email_allow_anonymous_if_email_present",
                "feedback_email_throttle_per_order",
                "feedback_email_subject",
            ]

            settings = {}
            for key in settings_keys:
                config = db_session.execute(
                    select(SystemSetting).where(SystemSetting.key == key)
                ).scalar_one_or_none()
                settings[key] = config.value if config else None

            return jsonify({"data": settings}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting feedback settings: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al obtener configuraciones"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_config_bp.post("/settings/feedback")
def save_feedback_settings():
    """Save all feedback-related settings."""

    from shared.models import SystemSetting

    try:
        payload = request.get_json(silent=True) or {}
        settings_keys = [
            "feedback_prompt_enabled",
            "feedback_prompt_timeout_seconds",
            "feedback_email_enabled",
            "feedback_email_token_ttl_hours",
            "feedback_email_allow_anonymous_if_email_present",
            "feedback_email_throttle_per_order",
            "feedback_email_subject",
        ]

        with get_session() as db_session:
            for key in settings_keys:
                if key in payload:
                    config = db_session.execute(
                        select(SystemSetting).where(SystemSetting.key == key)
                    ).scalar_one_or_none()

                    if config:
                        config.value = str(payload[key])
                    else:
                        config = SystemSetting(
                            key=key,
                            value=str(payload[key]),
                            value_type="string",
                            description=f"Feedback setting: {key}",
                            category="feedback",
                        )
                        db_session.add(config)

            db_session.commit()

            return jsonify({"success": True, "message": "Configuraciones guardadas"}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error saving feedback settings: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al guardar configuraciones"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
