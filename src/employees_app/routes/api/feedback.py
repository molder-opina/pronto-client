"""
Feedback API - Endpoints para sistema de calificación y feedback
Handles customer feedback for waiters, food quality, and overall experience
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from employees_app.decorators import login_required
from shared.jwt_middleware import jwt_required
from shared.logging_config import get_logger
from shared.schemas import BulkFeedbackRequest, FeedbackRequest
from shared.serializers import error_response, success_response
from shared.services.feedback_service import FeedbackService

# Create blueprint
feedback_bp = Blueprint("feedback", __name__)
logger = get_logger(__name__)


@feedback_bp.get("/feedback")
@jwt_required
def get_all_feedback():
    """
    Get feedback with pagination
    Requires login

    Query params:
        - session_id: int (optional) - Filter by session
        - employee_id: int (optional) - Filter by employee
        - limit: int (default: 50)
        - offset: int (default: 0)
    """
    session_id = request.args.get("session_id", type=int)
    employee_id = request.args.get("employee_id", type=int)
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)

    try:
        if session_id:
            feedback = FeedbackService.get_feedback_by_session(session_id)
            return jsonify(
                success_response({"feedback": feedback, "total": len(feedback)})
            ), HTTPStatus.OK

        if employee_id:
            result = FeedbackService.get_feedback_by_employee(
                employee_id, limit=limit, offset=offset
            )
            return jsonify(success_response(result)), HTTPStatus.OK

        return jsonify(
            error_response("Debe proporcionar session_id o employee_id")
        ), HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.error(f"Error getting feedback: {e}")
        return jsonify(
            error_response("Error al obtener feedback")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.get("/feedback/<int:feedback_id>")
@jwt_required
def get_feedback(feedback_id: int):
    """
    Get a specific feedback entry by ID
    Requires login
    """
    try:
        feedback = FeedbackService.get_feedback_by_id(feedback_id)

        if not feedback:
            return jsonify(error_response("Feedback no encontrado")), HTTPStatus.NOT_FOUND

        return jsonify(success_response(feedback)), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting feedback {feedback_id}: {e}")
        return jsonify(
            error_response("Error al obtener feedback")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.post("/feedback")
def create_feedback():
    """
    Create a new feedback entry
    Public endpoint - no authentication required (for customer feedback)

    Body: FeedbackRequest schema
    """
    payload = request.get_json(silent=True) or {}

    try:
        # Validate request
        validated_data = FeedbackRequest(**payload)

        # Create feedback
        feedback = FeedbackService.create_feedback(validated_data.dict())

        logger.info(f"Feedback created for session {validated_data.session_id}")
        return jsonify(success_response(feedback)), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except ValueError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error creating feedback: {e}")
        return jsonify(error_response("Error al crear feedback")), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.post("/feedback/bulk")
def create_bulk_feedback():
    """
    Create multiple feedback entries at once
    Public endpoint - no authentication required

    Body: BulkFeedbackRequest schema
    """
    payload = request.get_json(silent=True) or {}

    try:
        # Validate request
        validated_data = BulkFeedbackRequest(**payload)

        # Create feedback
        feedback_list = FeedbackService.create_bulk_feedback(
            validated_data.session_id,
            validated_data.employee_id,
            validated_data.feedback_items,
            validated_data.is_anonymous,
        )

        logger.info(
            f"Bulk feedback created for session {validated_data.session_id}: {len(feedback_list)} items"
        )
        return jsonify(success_response({"feedback": feedback_list})), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except ValueError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error creating bulk feedback: {e}")
        return jsonify(error_response("Error al crear feedback")), HTTPStatus.INTERNAL_SERVER_ERROR


# Statistics endpoints
@feedback_bp.get("/feedback/stats/employee/<int:employee_id>")
@jwt_required
def get_employee_stats(employee_id: int):
    """
    Get aggregated feedback statistics for an employee
    Requires login

    Query params:
        - days: int (default: 30) - Period in days for statistics
    """
    days = request.args.get("days", default=30, type=int)

    try:
        stats = FeedbackService.get_employee_stats(employee_id, days=days)
        return jsonify(success_response(stats)), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting employee stats for {employee_id}: {e}")
        return jsonify(
            error_response("Error al obtener estadísticas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.get("/feedback/stats/overall")
@jwt_required
def get_overall_stats():
    """
    Get overall feedback statistics for the business
    Requires login

    Query params:
        - days: int (default: 30) - Period in days for statistics
        - category: str (optional) - Filter by category
    """
    days = request.args.get("days", default=30, type=int)
    category = request.args.get("category")

    try:
        stats = FeedbackService.get_overall_stats(days=days, category=category)
        return jsonify(success_response(stats)), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting overall stats: {e}")
        return jsonify(
            error_response("Error al obtener estadísticas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.get("/feedback/stats/top-employees")
@jwt_required
def get_top_rated_employees():
    """
    Get top-rated employees based on recent feedback
    Requires login

    Query params:
        - limit: int (default: 10) - Number of employees to return
        - days: int (default: 30) - Period in days for statistics
        - category: str (optional) - Filter by category
    """
    limit = request.args.get("limit", default=10, type=int)
    days = request.args.get("days", default=30, type=int)
    category = request.args.get("category")

    try:
        top_employees = FeedbackService.get_top_rated_employees(
            limit=limit, days=days, category=category
        )
        return jsonify(success_response({"employees": top_employees})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting top rated employees: {e}")
        return jsonify(
            error_response("Error al obtener empleados destacados")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@feedback_bp.get("/feedback/session/<int:session_id>")
def get_session_feedback(session_id: int):
    """
    Get all feedback for a specific session
    Public endpoint - useful for customers to see their submitted feedback
    """
    try:
        feedback = FeedbackService.get_feedback_by_session(session_id)
        return jsonify(success_response({"feedback": feedback})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting feedback for session {session_id}: {e}")
        return jsonify(
            error_response("Error al obtener feedback")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
