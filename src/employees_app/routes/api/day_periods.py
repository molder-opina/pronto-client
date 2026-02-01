"""
API endpoints to manage day period definitions (mañana, tarde, noche, etc.).
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.logging_config import get_logger
from shared.serializers import error_response, success_response
from shared.services.day_period_service import DayPeriodService

day_periods_bp = Blueprint("day_periods", __name__)
logger = get_logger(__name__)


@day_periods_bp.get("/day-periods")
@admin_required
def list_day_periods():
    """Return all configured day periods."""
    try:
        periods = DayPeriodService.list_periods()
        return jsonify(success_response({"periods": periods, "total": len(periods)})), HTTPStatus.OK
    except Exception:
        logger.exception("Error listing day periods")
        return jsonify(
            error_response("Error al obtener periodos del día")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@day_periods_bp.post("/day-periods")
@admin_required
def create_day_period():
    """Create a new day period definition."""
    payload = request.get_json(silent=True) or {}
    payload.setdefault("display_order", 999)

    try:
        period = DayPeriodService.create_period(payload)
        logger.info("Day period %s created by employee %s", period["key"], get_employee_id())
        return jsonify(success_response({"period": period})), HTTPStatus.CREATED
    except ValueError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
    except Exception:
        logger.exception("Error creating day period")
        return jsonify(
            error_response("Error al crear periodo del día")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@day_periods_bp.put("/day-periods/<int:period_id>")
@admin_required
def update_day_period(period_id: int):
    """Update an existing day period."""
    payload = request.get_json(silent=True) or {}
    try:
        period = DayPeriodService.update_period(period_id, payload)
        if not period:
            return jsonify(error_response("Periodo no encontrado")), HTTPStatus.NOT_FOUND
        logger.info("Day period %s updated by employee %s", period_id, get_employee_id())
        return jsonify(success_response({"period": period})), HTTPStatus.OK
    except ValueError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
    except Exception:
        logger.exception("Error updating day period %s", period_id)
        return jsonify(
            error_response("Error al actualizar periodo del día")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@day_periods_bp.delete("/day-periods/<int:period_id>")
@admin_required
def delete_day_period(period_id: int):
    """Delete a day period definition."""
    try:
        deleted = DayPeriodService.delete_period(period_id)
        if not deleted:
            return jsonify(error_response("Periodo no encontrado")), HTTPStatus.NOT_FOUND
        logger.info("Day period %s deleted by employee %s", period_id, get_employee_id())
        return jsonify(success_response({"message": "Periodo eliminado"})), HTTPStatus.OK
    except Exception:
        logger.exception("Error deleting day period %s", period_id)
        return jsonify(
            error_response("Error al eliminar periodo del día")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
