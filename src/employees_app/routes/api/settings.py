"""
System Settings API - Endpoints para configuración avanzada del sistema
Handles system-wide settings (Firefox about:config style)
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.logging_config import get_logger
from shared.schemas import SystemSettingRequest
from shared.serializers import error_response, success_response
from shared.services.settings_service import SettingsService

# Create blueprint
settings_bp = Blueprint("settings", __name__)
logger = get_logger(__name__)


@settings_bp.get("/settings")
@admin_required
def get_all_settings():
    """
    Get all system settings (about:config style)
    Requires admin permissions

    Query params:
        - category: str (optional) - Filter by category
        - search: str (optional) - Search in key or description
    """
    category = request.args.get("category")
    search = request.args.get("search", "").lower()

    try:
        settings = SettingsService.get_all_settings(category=category)

        # Apply search filter if provided
        if search:
            settings = [
                s
                for s in settings
                if search in s["key"].lower()
                or (s["description"] and search in s["description"].lower())
            ]

        # Group by category for easier UI rendering
        categories = {}
        for setting in settings:
            cat = setting["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(setting)

        return jsonify(
            success_response(
                {"settings": settings, "by_category": categories, "total": len(settings)}
            )
        ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return jsonify(
            error_response("Error al obtener configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.get("/settings/<string:key>")
@admin_required
def get_setting(key: str):
    """
    Get a specific setting by key
    Requires admin permissions
    """
    try:
        value = SettingsService.get_setting(key)

        if value is None:
            return jsonify(error_response("Configuración no encontrada")), HTTPStatus.NOT_FOUND

        return jsonify(success_response({"key": key, "value": value})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return jsonify(
            error_response("Error al obtener configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.get("/settings/public/<string:key>")
@jwt_required
def get_public_setting(key: str):
    """
    Get a specific public setting by key
    Requires login (for employees to read certain settings like notification sounds)

    Allowed keys:
    - waiter_notification_sound: Sound type for waiter notifications
    """
    # Whitelist of settings that employees can read
    ALLOWED_PUBLIC_SETTINGS = {"waiter_notification_sound"}

    if key not in ALLOWED_PUBLIC_SETTINGS:
        return jsonify(
            error_response("Configuración no disponible públicamente")
        ), HTTPStatus.FORBIDDEN

    try:
        value = SettingsService.get_setting(key)

        if value is None:
            return jsonify(error_response("Configuración no encontrada")), HTTPStatus.NOT_FOUND

        return jsonify(success_response({"key": key, "value": value})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error getting public setting {key}: {e}")
        return jsonify(
            error_response("Error al obtener configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.post("/settings")
@admin_required
def create_or_update_setting():
    """
    Create or update a system setting
    Requires admin permissions

    Body: SystemSettingRequest schema
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    try:
        # Validate request
        validated_data = SystemSettingRequest(**payload)

        # Set setting
        result = SettingsService.set_setting(
            validated_data.key, validated_data.value, employee_id=employee_id
        )

        logger.info(f"Setting {validated_data.key} updated by employee {employee_id}")
        return jsonify(success_response(result)), HTTPStatus.OK

    except ValidationError as e:
        return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        return jsonify(
            error_response("Error al actualizar configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.put("/settings/<string:key>")
@admin_required
def update_setting_by_key(key: str):
    """
    Update a specific setting by key
    Requires admin permissions

    Body: {
        "value": any (string, int, bool, etc.)
    }
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    try:
        value = payload.get("value")
        if value is None:
            return jsonify(error_response("El campo 'value' es requerido")), HTTPStatus.BAD_REQUEST

        # Update setting
        result = SettingsService.set_setting(key, value, employee_id=employee_id)

        logger.info(f"Setting {key} updated to {value} by employee {employee_id}")
        return jsonify(success_response(result)), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        return jsonify(
            error_response("Error al actualizar configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.post("/settings/bulk")
@admin_required
def bulk_update_settings():
    """
    Update multiple settings at once
    Requires admin permissions

    Body: {
        "settings": [
            {"key": "setting1", "value": "value1"},
            {"key": "setting2", "value": "value2"}
        ]
    }
    """
    payload = request.get_json(silent=True) or {}
    settings_data = payload.get("settings", [])
    employee_id = get_employee_id()

    try:
        if not settings_data:
            return jsonify(
                error_response("El campo 'settings' es requerido")
            ), HTTPStatus.BAD_REQUEST

        results = []
        for setting_data in settings_data:
            key = setting_data.get("key")
            value = setting_data.get("value")

            if not key:
                continue

            result = SettingsService.set_setting(key, value, employee_id=employee_id)
            results.append(result)

        logger.info(f"Bulk settings update by employee {employee_id}: {len(results)} settings")
        return jsonify(success_response({"settings": results})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error bulk updating settings: {e}")
        return jsonify(
            error_response("Error al actualizar configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.post("/settings/initialize")
@admin_required
def initialize_default_settings():
    """
    Initialize default settings in the database
    Requires admin permissions

    This is useful for first-time setup or after database reset
    """
    try:
        SettingsService.initialize_defaults()

        logger.info(f"Default settings initialized by employee {get_employee_id()}")
        return jsonify(
            success_response({"message": "Configuración por defecto inicializada"})
        ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error initializing default settings: {e}")
        return jsonify(
            error_response("Error al inicializar configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_bp.get("/settings/categories")
@admin_required
def get_setting_categories():
    """
    Get list of all setting categories
    Requires admin permissions
    """
    try:
        settings = SettingsService.get_all_settings()
        categories = list({s["category"] for s in settings})
        categories.sort()

        # Count settings per category
        category_counts = {}
        for cat in categories:
            category_counts[cat] = len([s for s in settings if s["category"] == cat])

        return jsonify(
            success_response({"categories": categories, "counts": category_counts})
        ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return jsonify(
            error_response("Error al obtener categorías")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
