"""
Business Info API - Endpoints para información de negocio y horarios
Handles business information, logo, schedule, and contact details
"""

import uuid
from http import HTTPStatus
from pathlib import Path

from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from werkzeug.utils import secure_filename

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.logging_config import get_logger
from shared.schemas import BusinessInfoRequest, BusinessScheduleRequest
from shared.serializers import error_response, success_response
from shared.services.business_info_service import BusinessInfoService, BusinessScheduleService

# Create blueprint
business_info_bp = Blueprint("business_info", __name__)
logger = get_logger(__name__)


@business_info_bp.get("/business-info")
@jwt_required
def get_business_info():
    """
    Get business information (name, address, logo, etc.)
    Public endpoint - no special permissions required
    """
    try:
        info = BusinessInfoService.get_business_info()

        if not info:
            return jsonify(
                success_response(
                    {
                        "business_name": "Mi Restaurante",
                        "currency": "MXN",
                        "timezone": "America/Mexico_City",
                    }
                )
            ), HTTPStatus.OK

        return jsonify(success_response(info)), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting business info: {e}")
        return jsonify(
            error_response("Error al obtener información del negocio")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.post("/business-info")
@admin_required
def create_or_update_business_info():
    """
    Create or update business information
    Requires admin permissions

    Body: BusinessInfoRequest schema
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    try:
        # Validate request
        validated_data = BusinessInfoRequest(**payload)

        # Create/update
        info = BusinessInfoService.create_or_update_business_info(
            validated_data.dict(), employee_id=employee_id
        )

        logger.info(f"Business info updated by employee {employee_id}")
        return jsonify(success_response(info)), HTTPStatus.OK

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error updating business info: {e}")
        return jsonify(
            error_response("Error al actualizar información del negocio")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.post("/business-info/upload-logo")
@admin_required
def upload_logo():
    """
    Upload a logo file for the business
    Requires admin permissions

    Form Data:
        - logo: Image file (PNG, JPG, SVG, WebP - max 2MB)

    Returns:
        - logo_url: URL of the uploaded logo
    """
    # Check if file was uploaded
    if "logo" not in request.files:
        return jsonify(error_response("No se proporcionó archivo")), HTTPStatus.BAD_REQUEST

    file = request.files["logo"]

    # Check if file has a filename
    if file.filename == "":
        return jsonify(error_response("Nombre de archivo vacío")), HTTPStatus.BAD_REQUEST

    # Validate file extension
    allowed_extensions = {"png", "jpg", "jpeg", "svg", "webp"}
    file_ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else ""

    if file_ext not in allowed_extensions:
        return jsonify(
            error_response(f"Formato no válido. Use: {', '.join(allowed_extensions)}")
        ), HTTPStatus.BAD_REQUEST

    try:
        # Generate unique filename
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = secure_filename(file.filename)
        filename_parts = safe_filename.rsplit(".", 1)
        new_filename = (
            f"logo_{unique_id}.{filename_parts[1]}"
            if len(filename_parts) > 1
            else f"logo_{unique_id}"
        )

        # Define upload directory (static/uploads/logos)
        upload_dir = (
            Path(__file__).parent.parent.parent.parent / "static_content" / "uploads" / "logos"
        )
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = upload_dir / new_filename
        file.save(str(file_path))

        # Generate URL
        logo_url = f"/static/uploads/logos/{new_filename}"

        # Update business info with new logo URL
        employee_id = get_employee_id()
        BusinessInfoService.create_or_update_business_info(
            {"logo_url": logo_url}, employee_id=employee_id
        )

        logger.info(f"Logo uploaded by employee {employee_id}: {logo_url}")

        return jsonify(
            success_response({"logo_url": logo_url, "filename": new_filename})
        ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error uploading logo: {e}")
        return jsonify(error_response("Error al subir logo")), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.get("/business-schedule")
@jwt_required
def get_business_schedule():
    """
    Get complete business schedule for all days
    Returns schedule for Monday-Sunday with opening hours
    """
    try:
        schedule = BusinessScheduleService.get_schedule()
        return jsonify(success_response({"schedule": schedule})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting business schedule: {e}")
        return jsonify(error_response("Error al obtener horario")), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.get("/business-schedule/<int:day_of_week>")
@jwt_required
def get_schedule_for_day(day_of_week: int):
    """
    Get schedule for a specific day

    Path params:
        - day_of_week: 0 (Monday) to 6 (Sunday)
    """
    try:
        if day_of_week < 0 or day_of_week > 6:
            return jsonify(
                error_response("day_of_week debe estar entre 0 y 6")
            ), HTTPStatus.BAD_REQUEST

        schedule = BusinessScheduleService.get_schedule_for_day(day_of_week)
        return jsonify(success_response(schedule)), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error getting schedule for day {day_of_week}: {e}")
        return jsonify(error_response("Error al obtener horario")), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.put("/business-schedule/<int:day_of_week>")
@admin_required
def update_schedule_for_day(day_of_week: int):
    """
    Update schedule for a specific day
    Requires admin permissions

    Body: BusinessScheduleRequest schema (without day_of_week)
    """
    payload = request.get_json(silent=True) or {}

    try:
        if day_of_week < 0 or day_of_week > 6:
            return jsonify(
                error_response("day_of_week debe estar entre 0 y 6")
            ), HTTPStatus.BAD_REQUEST

        # Add day_of_week to payload for validation
        payload["day_of_week"] = day_of_week

        # Validate request
        validated_data = BusinessScheduleRequest(**payload)

        # Remove day_of_week before updating (it's in the URL)
        update_data = validated_data.dict()
        update_data.pop("day_of_week")

        # Update schedule
        schedule = BusinessScheduleService.update_schedule(day_of_week, update_data)

        logger.info(f"Schedule for day {day_of_week} updated by employee {get_employee_id()}")
        return jsonify(success_response(schedule)), HTTPStatus.OK

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error updating schedule for day {day_of_week}: {e}")
        return jsonify(
            error_response("Error al actualizar horario")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@business_info_bp.post("/business-schedule/bulk")
@admin_required
def bulk_update_schedule():
    """
    Update multiple days at once
    Requires admin permissions

    Body: {
        "schedules": [
            {
                "day_of_week": 0,
                "is_open": true,
                "open_time": "09:00",
                "close_time": "22:00",
                "notes": null
            },
            ...
        ]
    }
    """
    payload = request.get_json(silent=True) or {}
    schedules_data = payload.get("schedules", [])

    try:
        if not schedules_data:
            return jsonify(
                error_response("El campo 'schedules' es requerido")
            ), HTTPStatus.BAD_REQUEST

        # Validate all schedules
        validated_schedules = []
        for schedule_data in schedules_data:
            validated = BusinessScheduleRequest(**schedule_data)
            validated_schedules.append(validated.dict())

        # Update all
        updated = BusinessScheduleService.bulk_update_schedule(validated_schedules)

        logger.info(f"Bulk schedule update by employee {get_employee_id()}")
        return jsonify(success_response({"schedules": updated})), HTTPStatus.OK

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error bulk updating schedule: {e}")
        return jsonify(
            error_response("Error al actualizar horarios")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
