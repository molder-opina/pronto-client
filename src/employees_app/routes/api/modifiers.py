"""
Modifiers API - Gestión de modificadores de productos

Este módulo maneja la creación, actualización y eliminación de grupos de
modificadores y modificadores individuales para items del menú.
"""

from decimal import Decimal
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from employees_app.decorators import admin_required
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Modifier, ModifierGroup
from shared.serializers import error_response, success_response

modifiers_bp = Blueprint("modifiers", __name__)
logger = get_logger(__name__)


@modifiers_bp.get("/modifiers")
def get_modifiers():
    """
    Obtiene todos los grupos de modificadores con sus modificadores.

    Returns: Lista de grupos con sus modificadores anidados, ordenados por display_order
    """
    with get_session() as session:
        groups = (
            session.execute(select(ModifierGroup).order_by(ModifierGroup.display_order))
            .scalars()
            .all()
        )

        result = []
        for group in groups:
            modifiers = (
                session.execute(
                    select(Modifier)
                    .where(Modifier.group_id == group.id)
                    .order_by(Modifier.display_order)
                )
                .scalars()
                .all()
            )

            result.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "min_selection": group.min_selection,
                    "max_selection": group.max_selection,
                    "is_required": group.is_required,
                    "display_order": group.display_order,
                    "modifiers": [
                        {
                            "id": mod.id,
                            "name": mod.name,
                            "price_adjustment": float(mod.price_adjustment),
                            "is_available": mod.is_available,
                            "display_order": mod.display_order,
                        }
                        for mod in modifiers
                    ],
                }
            )

        return jsonify({"modifier_groups": result})


@modifiers_bp.post("/modifiers/groups")
@admin_required
def post_modifier_group():
    """
    Crea un nuevo grupo de modificadores.

    Body: {
        name: Nombre del grupo (requerido)
        description: Descripción del grupo (opcional)
        min_selection: Número mínimo de selecciones (default: 0)
        max_selection: Número máximo de selecciones (default: 1)
        is_required: Si el grupo es obligatorio (default: false)
        display_order: Orden de visualización (default: 0)
    }
    """
    payload = request.get_json(silent=True) or {}

    try:
        with get_session() as session:
            group = ModifierGroup(
                name=payload["name"],
                description=payload.get("description"),
                min_selection=payload.get("min_selection", 0),
                max_selection=payload.get("max_selection", 1),
                is_required=payload.get("is_required", False),
                display_order=payload.get("display_order", 0),
            )
            session.add(group)
            session.commit()
            session.refresh(group)

            return jsonify(
                success_response(
                    {
                        "id": group.id,
                        "name": group.name,
                        "description": group.description,
                        "min_selection": group.min_selection,
                        "max_selection": group.max_selection,
                        "is_required": group.is_required,
                        "display_order": group.display_order,
                    }
                )
            ), HTTPStatus.CREATED
    except KeyError as e:
        return jsonify(error_response(f"Campo requerido: {e}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error creating modifier group: {e}")
        return jsonify(
            error_response("Error al crear grupo de modificadores")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@modifiers_bp.put("/modifiers/groups/<int:group_id>")
@admin_required
def put_modifier_group(group_id: int):
    """
    Actualiza un grupo de modificadores existente.

    Body: {
        name: Nuevo nombre (opcional)
        description: Nueva descripción (opcional)
        min_selection: Nuevo mínimo de selecciones (opcional)
        max_selection: Nuevo máximo de selecciones (opcional)
        is_required: Nueva obligatoriedad (opcional)
        display_order: Nuevo orden de visualización (opcional)
    }
    """
    payload = request.get_json(silent=True) or {}

    try:
        with get_session() as session:
            group = session.execute(
                select(ModifierGroup).where(ModifierGroup.id == group_id)
            ).scalar_one_or_none()

            if not group:
                return jsonify(error_response("Grupo no encontrado")), HTTPStatus.NOT_FOUND

            if "name" in payload:
                group.name = payload["name"]
            if "description" in payload:
                group.description = payload["description"]
            if "min_selection" in payload:
                group.min_selection = payload["min_selection"]
            if "max_selection" in payload:
                group.max_selection = payload["max_selection"]
            if "is_required" in payload:
                group.is_required = payload["is_required"]
            if "display_order" in payload:
                group.display_order = payload["display_order"]

            session.commit()
            session.refresh(group)

            return jsonify(
                success_response(
                    {
                        "id": group.id,
                        "name": group.name,
                        "description": group.description,
                        "min_selection": group.min_selection,
                        "max_selection": group.max_selection,
                        "is_required": group.is_required,
                        "display_order": group.display_order,
                    }
                )
            )
    except Exception as e:
        logger.error(f"Error updating modifier group: {e}")
        return jsonify(
            error_response("Error al actualizar grupo de modificadores")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@modifiers_bp.post("/modifiers/groups/<int:group_id>/modifiers")
@admin_required
def post_modifier(group_id: int):
    """
    Añade un modificador a un grupo existente.

    Body: {
        name: Nombre del modificador (requerido)
        price_adjustment: Ajuste de precio (default: 0)
        is_available: Disponibilidad (default: true)
        display_order: Orden de visualización (default: 0)
    }
    """
    payload = request.get_json(silent=True) or {}

    try:
        with get_session() as session:
            group = session.execute(
                select(ModifierGroup).where(ModifierGroup.id == group_id)
            ).scalar_one_or_none()

            if not group:
                return jsonify(error_response("Grupo no encontrado")), HTTPStatus.NOT_FOUND

            modifier = Modifier(
                group_id=group_id,
                name=payload["name"],
                price_adjustment=Decimal(str(payload.get("price_adjustment", 0))),
                is_available=payload.get("is_available", True),
                display_order=payload.get("display_order", 0),
            )
            session.add(modifier)
            session.commit()
            session.refresh(modifier)

            return jsonify(
                success_response(
                    {
                        "id": modifier.id,
                        "group_id": modifier.group_id,
                        "name": modifier.name,
                        "price_adjustment": float(modifier.price_adjustment),
                        "is_available": modifier.is_available,
                        "display_order": modifier.display_order,
                    }
                )
            ), HTTPStatus.CREATED
    except KeyError as e:
        return jsonify(error_response(f"Campo requerido: {e}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error creating modifier: {e}")
        return jsonify(
            error_response("Error al crear modificador")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@modifiers_bp.put("/modifiers/<int:modifier_id>")
@admin_required
def put_modifier(modifier_id: int):
    """
    Actualiza un modificador existente.

    Body: {
        name: Nuevo nombre (opcional)
        price_adjustment: Nuevo ajuste de precio (opcional)
        is_available: Nueva disponibilidad (opcional)
        display_order: Nuevo orden de visualización (opcional)
    }
    """
    payload = request.get_json(silent=True) or {}

    try:
        with get_session() as session:
            modifier = session.execute(
                select(Modifier).where(Modifier.id == modifier_id)
            ).scalar_one_or_none()

            if not modifier:
                return jsonify(error_response("Modificador no encontrado")), HTTPStatus.NOT_FOUND

            if "name" in payload:
                modifier.name = payload["name"]
            if "price_adjustment" in payload:
                modifier.price_adjustment = Decimal(str(payload["price_adjustment"]))
            if "is_available" in payload:
                modifier.is_available = payload["is_available"]
            if "display_order" in payload:
                modifier.display_order = payload["display_order"]

            session.commit()
            session.refresh(modifier)

            return jsonify(
                success_response(
                    {
                        "id": modifier.id,
                        "group_id": modifier.group_id,
                        "name": modifier.name,
                        "price_adjustment": float(modifier.price_adjustment),
                        "is_available": modifier.is_available,
                        "display_order": modifier.display_order,
                    }
                )
            )
    except Exception as e:
        logger.error(f"Error updating modifier: {e}")
        return jsonify(
            error_response("Error al actualizar modificador")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@modifiers_bp.delete("/modifiers/<int:modifier_id>")
@admin_required
def delete_modifier(modifier_id: int):
    """
    Elimina un modificador permanentemente.

    Nota: Esto eliminará el modificador de la base de datos.
    """
    try:
        with get_session() as session:
            modifier = session.execute(
                select(Modifier).where(Modifier.id == modifier_id)
            ).scalar_one_or_none()

            if not modifier:
                return jsonify(error_response("Modificador no encontrado")), HTTPStatus.NOT_FOUND

            session.delete(modifier)
            session.commit()

            return jsonify(success_response({"success": True}))
    except Exception as e:
        logger.error(f"Error deleting modifier: {e}")
        return jsonify(
            error_response("Error al eliminar modificador")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
