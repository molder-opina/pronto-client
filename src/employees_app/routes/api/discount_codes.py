"""
Discount Codes API - Gestión de códigos de descuento

Este módulo maneja la creación, actualización y eliminación de códigos
de descuento aplicables a órdenes.
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, jsonify, request

from employees_app.decorators import admin_required
from shared.db import get_session
from shared.jwt_middleware import jwt_required
from shared.logging_config import get_logger
from shared.models import DiscountCode
from shared.serializers import error_response, success_response

discount_codes_bp = Blueprint("discount_codes", __name__)
logger = get_logger(__name__)


@discount_codes_bp.get("/discount-codes")
@jwt_required
def get_all_discount_codes():
    """
    Obtiene todos los códigos de descuento.

    Returns: Lista de códigos ordenados por fecha de creación descendente
    """
    try:
        with get_session() as db:
            codes = db.query(DiscountCode).order_by(DiscountCode.created_at.desc()).all()

            data = []
            for code in codes:
                data.append(
                    {
                        "id": code.id,
                        "code": code.code,
                        "description": code.description,
                        "discount_type": code.discount_type,
                        "discount_percentage": float(code.discount_percentage)
                        if code.discount_percentage
                        else None,
                        "discount_amount": float(code.discount_amount)
                        if code.discount_amount
                        else None,
                        "min_purchase_amount": float(code.min_purchase_amount)
                        if code.min_purchase_amount
                        else None,
                        "usage_limit": code.usage_limit,
                        "times_used": code.times_used,
                        "applies_to": code.applies_to,
                        "valid_from": code.valid_from.isoformat(),
                        "valid_until": code.valid_until.isoformat() if code.valid_until else None,
                        "is_active": code.is_active,
                        "created_at": code.created_at.isoformat(),
                    }
                )

            return jsonify(success_response({"discount_codes": data})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching discount codes: {e}")
        # Evitar romper la UI si falta tabla/datos
        return jsonify(success_response({"discount_codes": []})), HTTPStatus.OK


@discount_codes_bp.post("/discount-codes")
@admin_required
def create_discount_code():
    """
    Crea un nuevo código de descuento.

    Body: {
        code: Código de descuento (requerido, se convertirá a mayúsculas)
        description: Descripción (opcional)
        discount_type: Tipo de descuento - 'percentage' o 'fixed' (requerido)
        discount_percentage: Porcentaje de descuento (requerido si type es 'percentage')
        discount_amount: Monto fijo de descuento (requerido si type es 'fixed')
        min_purchase_amount: Monto mínimo de compra (opcional)
        usage_limit: Límite de usos (opcional)
        applies_to: A qué aplica - 'all', etc. (default: 'all')
        valid_from: Fecha de inicio ISO (opcional, default: ahora)
        valid_until: Fecha de fin ISO (opcional)
        is_active: Estado activo (default: true)
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if "code" not in data or "discount_type" not in data:
            return jsonify(
                error_response("code y discount_type son requeridos")
            ), HTTPStatus.BAD_REQUEST

        # Validate discount type
        if data["discount_type"] not in ["percentage", "fixed"]:
            return jsonify(
                error_response("discount_type debe ser 'percentage' o 'fixed'")
            ), HTTPStatus.BAD_REQUEST

        # Validate discount values
        if data["discount_type"] == "percentage":
            if "discount_percentage" not in data:
                return jsonify(
                    error_response("discount_percentage es requerido para tipo percentage")
                ), HTTPStatus.BAD_REQUEST
        elif data["discount_type"] == "fixed":
            if "discount_amount" not in data:
                return jsonify(
                    error_response("discount_amount es requerido para tipo fixed")
                ), HTTPStatus.BAD_REQUEST

        # Normalize code to uppercase
        code = data["code"].strip().upper()

        # Check if code already exists
        with get_session() as db:
            existing = db.query(DiscountCode).filter(DiscountCode.code == code).first()
            if existing:
                return jsonify(error_response("El código ya existe")), HTTPStatus.CONFLICT

            # Parse dates
            valid_from = (
                datetime.fromisoformat(data["valid_from"])
                if "valid_from" in data
                else datetime.utcnow()
            )
            valid_until = (
                datetime.fromisoformat(data["valid_until"]) if data.get("valid_until") else None
            )

            discount_code = DiscountCode(
                code=code,
                description=data.get("description"),
                discount_type=data["discount_type"],
                discount_percentage=data.get("discount_percentage"),
                discount_amount=data.get("discount_amount"),
                min_purchase_amount=data.get("min_purchase_amount"),
                usage_limit=data.get("usage_limit"),
                times_used=0,
                applies_to=data.get("applies_to", "all"),
                valid_from=valid_from,
                valid_until=valid_until,
                is_active=data.get("is_active", True),
            )

            db.add(discount_code)
            db.commit()
            db.refresh(discount_code)

            return jsonify(
                success_response(
                    {
                        "discount_code": {
                            "id": discount_code.id,
                            "code": discount_code.code,
                            "description": discount_code.description,
                            "is_active": discount_code.is_active,
                        }
                    }
                )
            ), HTTPStatus.CREATED

    except ValueError as e:
        return jsonify(error_response(f"Formato de fecha inválido: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error creating discount code: {e}")
        return jsonify(
            error_response("Error al crear código de descuento")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@discount_codes_bp.patch("/discount-codes/<int:code_id>")
@admin_required
def update_discount_code(code_id: int):
    """
    Actualiza un código de descuento existente.

    Body: Cualquier campo del código que se desee actualizar
    """
    try:
        data = request.get_json()

        with get_session() as db:
            discount_code = db.query(DiscountCode).filter(DiscountCode.id == code_id).first()
            if not discount_code:
                return jsonify(
                    error_response("Código de descuento no encontrado")
                ), HTTPStatus.NOT_FOUND

            # Update fields if provided
            if "code" in data:
                code = data["code"].strip().upper()
                # Check if new code already exists
                existing = (
                    db.query(DiscountCode)
                    .filter(DiscountCode.code == code, DiscountCode.id != code_id)
                    .first()
                )
                if existing:
                    return jsonify(error_response("El código ya existe")), HTTPStatus.CONFLICT
                discount_code.code = code

            if "description" in data:
                discount_code.description = data["description"]
            if "discount_type" in data:
                discount_code.discount_type = data["discount_type"]
            if "discount_percentage" in data:
                discount_code.discount_percentage = data["discount_percentage"]
            if "discount_amount" in data:
                discount_code.discount_amount = data["discount_amount"]
            if "min_purchase_amount" in data:
                discount_code.min_purchase_amount = data["min_purchase_amount"]
            if "usage_limit" in data:
                discount_code.usage_limit = data["usage_limit"]
            if "applies_to" in data:
                discount_code.applies_to = data["applies_to"]
            if "valid_from" in data:
                discount_code.valid_from = datetime.fromisoformat(data["valid_from"])
            if "valid_until" in data:
                discount_code.valid_until = (
                    datetime.fromisoformat(data["valid_until"]) if data["valid_until"] else None
                )
            if "is_active" in data:
                discount_code.is_active = bool(data["is_active"])

            db.commit()
            db.refresh(discount_code)

            return jsonify(
                success_response(
                    {
                        "discount_code": {
                            "id": discount_code.id,
                            "code": discount_code.code,
                            "is_active": discount_code.is_active,
                        }
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Formato de fecha inválido: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error updating discount code: {e}")
        return jsonify(
            error_response("Error al actualizar código de descuento")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@discount_codes_bp.delete("/discount-codes/<int:code_id>")
@admin_required
def delete_discount_code(code_id: int):
    """
    Elimina un código de descuento permanentemente.

    Nota: Esta es una eliminación física, el código se borrará de la base de datos.
    """
    try:
        with get_session() as db:
            discount_code = db.query(DiscountCode).filter(DiscountCode.id == code_id).first()
            if not discount_code:
                return jsonify(
                    error_response("Código de descuento no encontrado")
                ), HTTPStatus.NOT_FOUND

            db.delete(discount_code)
            db.commit()

            return jsonify(
                success_response({"message": "Código de descuento eliminado correctamente"})
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error deleting discount code: {e}")
        return jsonify(
            error_response("Error al eliminar código de descuento")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
