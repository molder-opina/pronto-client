"""
Config API - Endpoints para configuración de negocio
Handles business configuration parameters
"""

import json
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import BusinessConfig
from shared.serializers import error_response, success_response

# Create blueprint without url_prefix (inherited from parent)
config_bp = Blueprint("config", __name__)
logger = get_logger(__name__)


@config_bp.get("/config")
@jwt_required
def get_business_config():
    """
    Obtener toda la configuración de negocio

    Query params:
        - category: str (opcional) - Filtrar por categoría

    Retorna todas las configuraciones con sus valores parseados según tipo.
    """
    category = request.args.get("category")

    def _parse_value(config: BusinessConfig):
        value = config.config_value
        value_type = (config.value_type or "string").lower()
        if value is None:
            return None
        if value_type == "int":
            try:
                return int(value)
            except ValueError:
                return value
        if value_type == "float":
            try:
                return float(value)
            except ValueError:
                return value
        if value_type == "bool":
            return str(value).lower() in {"true", "1", "yes"}
        if value_type == "json":
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return value
        return value

    with get_session() as db_session:
        query = select(BusinessConfig).order_by(
            BusinessConfig.category, BusinessConfig.display_name
        )

        if category:
            query = query.where(BusinessConfig.category == category)

        configs = db_session.execute(query).scalars().all()

        result = []
        for config in configs:
            parsed_value = _parse_value(config)
            result.append(
                {
                    "id": config.id,
                    "key": config.config_key,
                    "value": parsed_value,
                    "raw_value": config.config_value,
                    "value_type": config.value_type,
                    "category": config.category,
                    "display_name": config.display_name,
                    "description": config.description,
                    "min_value": float(config.min_value) if config.min_value else None,
                    "max_value": float(config.max_value) if config.max_value else None,
                    "unit": config.unit,
                    "updated_at": config.updated_at.isoformat() if config.updated_at else None,
                }
            )

        return jsonify({"configs": result})


@config_bp.get("/config/<string:config_key>")
def get_single_config(config_key: str):
    """
    Obtener configuración específica por key

    Endpoint público para clientes. Retorna valor sin parsing.
    """
    with get_session() as db_session:
        config = (
            db_session.execute(
                select(BusinessConfig).where(BusinessConfig.config_key == config_key)
            )
            .scalars()
            .one_or_none()
        )

        if not config:
            return jsonify(error_response("Configuración no encontrada")), HTTPStatus.NOT_FOUND

        return jsonify(
            {
                "key": config.config_key,
                "value": config.config_value,
                "value_type": config.value_type,
                "unit": config.unit,
            }
        )


@config_bp.put("/config/<int:config_id>")
@admin_required
def update_business_config(config_id: int):
    """
    Actualizar configuración de negocio

    Body:
        {
            "value": any - Nuevo valor (tipo depende de value_type)
        }

    Valida min/max para valores numéricos y formato para JSON.
    Requiere permisos de administrador.
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    try:
        with get_session() as db_session:
            config = (
                db_session.execute(select(BusinessConfig).where(BusinessConfig.id == config_id))
                .scalars()
                .one_or_none()
            )

            if not config:
                return jsonify(error_response("Configuración no encontrada")), HTTPStatus.NOT_FOUND

            new_value = payload.get("value")
            if new_value is None:
                return jsonify(
                    error_response("El campo 'value' es requerido")
                ), HTTPStatus.BAD_REQUEST

            # Validate min/max if applicable
            if config.value_type in ["int", "float"]:
                try:
                    numeric_value = float(new_value)
                    if config.min_value is not None and numeric_value < float(config.min_value):
                        return jsonify(
                            error_response(f"El valor debe ser al menos {config.min_value}")
                        ), HTTPStatus.BAD_REQUEST
                    if config.max_value is not None and numeric_value > float(config.max_value):
                        return jsonify(
                            error_response(f"El valor no puede exceder {config.max_value}")
                        ), HTTPStatus.BAD_REQUEST
                except ValueError:
                    return jsonify(
                        error_response("Valor numérico inválido")
                    ), HTTPStatus.BAD_REQUEST

            if config.value_type == "json":
                # Accept either JSON string or object
                try:
                    if isinstance(new_value, str):
                        json.loads(new_value)
                        config.config_value = new_value
                    else:
                        config.config_value = json.dumps(new_value)
                except (ValueError, TypeError):
                    return jsonify(error_response("Formato JSON inválido")), HTTPStatus.BAD_REQUEST
            elif config.value_type == "bool":
                config.config_value = (
                    "true" if str(new_value).lower() in {"true", "1", "yes", "on"} else "false"
                )
            else:
                config.config_value = str(new_value)
            config.updated_by = employee_id

            db_session.commit()

            logger.info(
                f"Config {config.config_key} updated to {new_value} by employee {employee_id}"
            )

            return jsonify(
                success_response(
                    {
                        "id": config.id,
                        "key": config.config_key,
                        "value": config.config_value,
                        "updated_at": config.updated_at.isoformat(),
                    }
                )
            )
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify(
            error_response("Error al actualizar configuración")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
