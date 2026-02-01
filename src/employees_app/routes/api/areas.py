"""
Areas API - Gestión de áreas/salones usando AreaService y base de datos.
Este módulo maneja las áreas del restaurante usando el modelo Area en PostgreSQL.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.models import Area, Table
from shared.serializers import error_response, success_response
from shared.services.area_service import AreaService
from shared.logging_config import get_logger

areas_bp = Blueprint("areas", __name__)
logger = get_logger(__name__)


@areas_bp.get("/areas")
@jwt_required
def list_areas():
    """Lista todas las áreas/salones."""
    try:
        areas = AreaService.list_areas(include_inactive=False, include_table_count=True)
        return jsonify(success_response({"areas": areas})), HTTPStatus.OK
    except Exception as exc:
        logger.error(f"Error listing areas: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR


@areas_bp.post("/areas")
@admin_required
def create_area():
    """Crea un área/salón."""
    payload = request.get_json(silent=True) or {}

    if not payload.get("name"):
        return jsonify(error_response("El nombre es requerido")), HTTPStatus.BAD_REQUEST

    try:
        area = AreaService.create_area(payload)
        return jsonify(success_response(area)), HTTPStatus.CREATED
    except Exception as exc:
        logger.error(f"Error creating area: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR


@areas_bp.put("/areas/<int:area_id>")
@admin_required
def update_area(area_id: int):
    """Actualiza un área existente."""
    payload = request.get_json(silent=True) or {}

    try:
        area = AreaService.update_area(area_id, payload)
        return jsonify(success_response(area)), HTTPStatus.OK
    except Exception as exc:
        logger.error(f"Error updating area {area_id}: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR


@areas_bp.delete("/areas/<int:area_id>")
@admin_required
def delete_area(area_id: int):
    """Elimina un área."""
    force = request.args.get("force", "false").lower() == "true"

    try:
        result = AreaService.delete_area(area_id, force=force)
        return jsonify(success_response(result)), HTTPStatus.OK
    except Exception as exc:
        logger.error(f"Error deleting area {area_id}: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR


@areas_bp.get("/areas/<int:area_id>")
@jwt_required
def get_area(area_id: int):
    """Obtiene un área específica con sus mesas."""
    try:
        area = AreaService.get_area(area_id)
        if not area:
            return jsonify(error_response("Área no encontrada")), HTTPStatus.NOT_FOUND
        return jsonify(success_response(area)), HTTPStatus.OK
    except Exception as exc:
        logger.error(f"Error getting area {area_id}: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR


@areas_bp.get("/areas/<int:area_id>/tables")
@jwt_required
def get_area_tables(area_id: int):
    """Obtiene todas las mesas de un área."""
    try:
        from shared.db import get_session

        with get_session() as db_session:
            area = (
                db_session.execute(select(Area).where(Area.id == area_id).where(Area.is_active))
                .scalars()
                .one_or_none()
            )

            if not area:
                return jsonify(error_response("Área no encontrada")), HTTPStatus.NOT_FOUND

            tables = (
                db_session.execute(
                    select(Table)
                    .where(Table.area_id == area_id)
                    .where(Table.is_active)
                    .order_by(Table.table_number)
                )
                .scalars()
                .all()
            )

            result = {
                "area": {
                    "id": area.id,
                    "name": area.name,
                    "color": area.color,
                    "prefix": area.prefix,
                },
                "tables": [
                    {
                        "id": table.id,
                        "table_number": table.table_number,
                        "qr_code": table.qr_code,
                        "capacity": table.capacity,
                        "status": table.status,
                        "position_x": table.position_x,
                        "position_y": table.position_y,
                        "shape": table.shape,
                    }
                    for table in tables
                ],
            }

            return jsonify(success_response(result)), HTTPStatus.OK
    except Exception as exc:
        logger.error(f"Error getting tables for area {area_id}: {exc}")
        return jsonify(error_response(str(exc))), HTTPStatus.INTERNAL_SERVER_ERROR
