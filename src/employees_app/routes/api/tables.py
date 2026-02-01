"""
Tables API - Gestión de mesas del restaurante

Este módulo maneja la creación, actualización, eliminación y generación
de códigos QR para las mesas del restaurante.
"""

import hashlib
import re
import time
from http import HTTPStatus
from io import BytesIO

import qrcode
from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import select, join

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_employee_id, jwt_required
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Area, Table
from shared.serializers import error_response, success_response
from shared.table_utils import build_table_code, validate_table_code
from shared.validation import ValidationError

tables_bp = Blueprint("tables", __name__)
logger = get_logger(__name__)


def _extract_digits(value: str) -> int:
    match = re.search(r"(\d+)", value or "")
    return int(match.group(1)) if match else 0


def _resolve_table_code(payload: dict) -> str:
    """
    Resolve and validate the table code from payload.
    Supports:
    - table_number provided as already formatted code (AREA-MNN)
    - explicit area_code + table_number integer
    """
    raw_table = payload.get("table_number")
    area_code = payload.get("area_code")

    if isinstance(raw_table, int):
        if not area_code:
            raise ValidationError(
                "area_code es requerido cuando se proporciona table_number como entero"
            )
        return build_table_code(area_code, raw_table)

    if isinstance(raw_table, str):
        raw_str = raw_table.strip()
        try:
            return validate_table_code(raw_str)
        except ValidationError:
            pass

        digits = _extract_digits(raw_str)
        if digits and area_code:
            return build_table_code(area_code, digits)

    raise ValidationError("El número de mesa es requerido y debe seguir el formato AREA-MNN.")


@tables_bp.get("/tables")
@jwt_required
def get_tables():
    """
    Obtiene todas las mesas con su estado e información.

    Query params:
    - area_id: Filtrar por área (opcional)
    - status: Filtrar por estado (opcional)
    """
    area_id = request.args.get("area_id")
    status = request.args.get("status")

    with get_session() as db_session:
        query = (
            select(Table, Area)
            .join(Area, Table.area_id == Area.id)
            .where(Table.is_active)
            .order_by(Area.prefix, Area.name, Table.table_number)
        )

        if area_id:
            query = query.where(Table.area_id == int(area_id))
        if status:
            query = query.where(Table.status == status)

        results = db_session.execute(query).all()

        result = []
        for table, area in results:
            result.append(
                {
                    "id": table.id,
                    "table_number": table.table_number,
                    "qr_code": table.qr_code,
                    "area": {
                        "id": area.id,
                        "prefix": area.prefix,
                        "name": area.name,
                        "color": area.color,
                    },
                    "capacity": table.capacity,
                    "status": table.status,
                    "position_x": table.position_x,
                    "position_y": table.position_y,
                    "shape": table.shape,
                    "notes": table.notes,
                    "created_at": table.created_at.isoformat() if table.created_at else None,
                }
            )

        return jsonify({"tables": result}), HTTPStatus.OK


@tables_bp.post("/tables")
@admin_required
def create_table():
    """
    Crea una nueva mesa (solo administradores).

    Body: {
        table_number: Número de mesa (requerido, formato AREA-MNN)
        area_id: ID del área (requerido)
        capacity: Capacidad de personas (default: 4)
        position_x: Posición X en el plano (opcional)
        position_y: Posición Y en el plano (opcional)
        shape: Forma de la mesa (default: 'square')
        notes: Notas adicionales (opcional)
    }
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    area_id = payload.get("area_id")
    if not area_id:
        return jsonify(error_response("area_id es requerido")), HTTPStatus.BAD_REQUEST

    try:
        try:
            table_number = _resolve_table_code(payload)
        except ValidationError as exc:
            return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST

        unique_string = f"{table_number}-{int(time.time())}"
        qr_code = hashlib.sha256(unique_string.encode()).hexdigest()[:16]

        with get_session() as db_session:
            new_table = Table(
                table_number=table_number,
                qr_code=qr_code,
                area_id=int(area_id),
                capacity=payload.get("capacity", 4),
                position_x=payload.get("position_x"),
                position_y=payload.get("position_y"),
                shape=payload.get("shape", "square"),
                notes=payload.get("notes"),
            )
            db_session.add(new_table)
            db_session.commit()
            db_session.refresh(new_table)

            logger.info(f"Table {table_number} created by employee {employee_id}")

            return jsonify(
                success_response(
                    {
                        "id": new_table.id,
                        "table_number": new_table.table_number,
                        "qr_code": new_table.qr_code,
                        "area_id": new_table.area_id,
                        "capacity": new_table.capacity,
                    }
                )
            ), HTTPStatus.CREATED
    except Exception as e:
        logger.error(f"Error creating table: {e}")
        return jsonify(error_response("Error al crear mesa")), HTTPStatus.INTERNAL_SERVER_ERROR


@tables_bp.put("/tables/<int:table_id>")
@admin_required
def update_table(table_id: int):
    """
    Actualiza una mesa existente (solo administradores).

    Body: {
        table_number: Nuevo número de mesa (opcional)
        area_id: Nueva área (opcional)
        capacity: Nueva capacidad (opcional)
        status: Nuevo estado (opcional)
        position_x: Nueva posición X (opcional)
        position_y: Nueva posición Y (opcional)
        shape: Nueva forma (opcional)
        notes: Nuevas notas (opcional)
        is_active: Estado de activación (opcional)
    }
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    try:
        with get_session() as db_session:
            table = (
                db_session.execute(select(Table).where(Table.id == table_id))
                .scalars()
                .one_or_none()
            )

            if not table:
                return jsonify(error_response("Mesa no encontrada")), HTTPStatus.NOT_FOUND

            if "table_number" in payload or "area_code" in payload:
                try:
                    table.table_number = _resolve_table_code(
                        {**payload, "table_number": payload.get("table_number", table.table_number)}
                    )
                except ValidationError as exc:
                    return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
            if "area_id" in payload:
                table.area_id = int(payload["area_id"])
            if "capacity" in payload:
                table.capacity = payload["capacity"]
            if "status" in payload:
                table.status = payload["status"]
            if "position_x" in payload:
                table.position_x = payload["position_x"]
            if "position_y" in payload:
                table.position_y = payload["position_y"]
            if "shape" in payload:
                table.shape = payload["shape"]
            if "notes" in payload:
                table.notes = payload["notes"]
            if "is_active" in payload:
                table.is_active = payload["is_active"]

            db_session.commit()
            db_session.refresh(table)

            logger.info(f"Table {table_id} updated by employee {employee_id}")

            return jsonify(
                success_response(
                    {
                        "id": table.id,
                        "table_number": table.table_number,
                        "area_id": table.area_id,
                        "capacity": table.capacity,
                        "status": table.status,
                    }
                )
            )
    except Exception as e:
        logger.error(f"Error updating table: {e}")
        return jsonify(error_response("Error al actualizar mesa")), HTTPStatus.INTERNAL_SERVER_ERROR


@tables_bp.delete("/tables/<int:table_id>")
@admin_required
def delete_table(table_id: int):
    """
    Desactiva una mesa (eliminación suave, solo administradores).

    La mesa no se elimina de la base de datos, solo se marca como inactiva.
    """
    employee_id = get_employee_id()

    try:
        with get_session() as db_session:
            table = (
                db_session.execute(select(Table).where(Table.id == table_id))
                .scalars()
                .one_or_none()
            )

            if not table:
                return jsonify(error_response("Mesa no encontrada")), HTTPStatus.NOT_FOUND

            table.is_active = False
            db_session.commit()

            logger.info(f"Table {table_id} deactivated by employee {employee_id}")

            return jsonify(success_response({"success": True}))
    except Exception as e:
        logger.error(f"Error deleting table: {e}")
        return jsonify(error_response("Error al eliminar mesa")), HTTPStatus.INTERNAL_SERVER_ERROR


@tables_bp.get("/tables/<int:table_id>/qr")
def get_table_qr(table_id: int):
    """
    Genera y retorna la imagen del código QR para una mesa.

    El código QR contiene la URL para acceder a la mesa desde la app de clientes.
    Returns: Imagen PNG del código QR
    """
    try:
        with get_session() as db_session:
            table = (
                db_session.execute(select(Table).where(Table.id == table_id))
                .scalars()
                .one_or_none()
            )

            if not table:
                return jsonify(error_response("Mesa no encontrada")), HTTPStatus.NOT_FOUND

            from flask import current_app

            base_url = current_app.config.get(
                "BASE_URL",
                f"http://localhost:{current_app.config.get('CLIENT_APP_HOST_PORT', 6080)}",
            )
            qr_url = f"{base_url}/menu?table={table.table_number}"

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(qr_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            img_buffer = BytesIO()
            img.save(img_buffer, format="PNG")
            img_buffer.seek(0)

            return send_file(
                img_buffer,
                mimetype="image/png",
                as_attachment=True,
                download_name=f"qr_mesa_{table.table_number}.png",
            )

    except Exception as e:
        logger.error(f"Error generating QR: {e}")
        return jsonify(
            error_response("Error al generar código QR")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
