"""
Promotions API - Gestión de promociones y descuentos

Este módulo maneja la creación, actualización y eliminación de promociones
y códigos de descuento con validación completa de datos.

Reglas de negocio:
- Las fechas son obligatorias (start_date, end_date)
- end_date debe ser mayor que start_date
- Estados: draft, active, expired (calculados automáticamente)
- Backend rechaza datos inválidos con HTTP 400
- Se loguean los registros excluidos de los listados
"""

import json
from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, jsonify, request

from employees_app.decorators import admin_required
from shared.db import get_session
from shared.jwt_middleware import jwt_required
from shared.logging_config import get_logger
from shared.models import Promotion
from shared.serializers import error_response, success_response

promotions_bp = Blueprint("promotions", __name__)
logger = get_logger(__name__)

PROMOTION_TYPES = {"percentage", "fixed", "bogo"}
DISCOUNT_TYPES = {"percentage", "fixed", "shipping"}
APPLIES_TO = {"all", "products", "tags", "package"}


def parse_json_field(value: str | None) -> list | None:
    """Parse a JSON string to list, returning None on failure or empty."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def calculate_promotion_status(
    valid_from: datetime, valid_until: datetime | None, is_active: bool
) -> str:
    """Calculate promotion status: draft, active, expired."""
    now = datetime.utcnow()
    if not is_active:
        return "inactive"
    if now < valid_from:
        return "draft"
    if valid_until and now > valid_until:
        return "expired"
    return "active"


def validate_promotion_data(data: dict) -> tuple[bool, str]:
    """
    Validate promotion data.
    Returns (is_valid, error_message).
    All validations must pass for HTTP 201/200.
    """
    if "name" not in data or not data["name"] or not data["name"].strip():
        return False, "El nombre de la promoción es obligatorio"

    if "promotion_type" not in data or data["promotion_type"] not in PROMOTION_TYPES:
        return False, "El tipo de promoción debe ser: percentage, fixed o bogo"

    if "applies_to" in data and data["applies_to"] not in APPLIES_TO:
        return False, "El campo 'applies_to' debe ser: all, products, tags o package"

    if "discount_percentage" in data:
        try:
            val = float(data["discount_percentage"])
            if val < 0 or val > 100:
                return False, "El porcentaje debe estar entre 0 y 100"
        except (ValueError, TypeError):
            return False, "El porcentaje debe ser un número válido"

    if "discount_amount" in data:
        try:
            val = float(data["discount_amount"])
            if val < 0:
                return False, "El monto no puede ser negativo"
        except (ValueError, TypeError):
            return False, "El monto debe ser un número válido"

    if data.get("min_purchase_amount"):
        try:
            val = float(data["min_purchase_amount"])
            if val < 0:
                return False, "El monto mínimo no puede ser negativo"
        except (ValueError, TypeError):
            return False, "El monto mínimo debe ser un número válido"

    return True, None


def validate_promotion_dates(data: dict) -> tuple[bool, str, datetime | None, datetime | None]:
    """
    Validate and parse promotion dates.
    Returns (is_valid, error_message, start_date, end_date).
    """
    today = datetime.utcnow()
    today + timedelta(days=30)

    if "start_date" not in data or not data["start_date"]:
        return False, "La fecha de inicio es obligatoria", None, None

    try:
        valid_from = datetime.fromisoformat(data["start_date"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False, "Formato de fecha de inicio inválido (YYYY-MM-DDTHH:MM:SS)", None, None

    if "end_date" not in data or not data["end_date"]:
        return False, "La fecha de fin es obligatoria", None, None

    try:
        valid_until = datetime.fromisoformat(data["end_date"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False, "Formato de fecha de fin inválido (YYYY-MM-DDTHH:MM:SS)", None, None

    if valid_until <= valid_from:
        return False, "La fecha de fin debe ser mayor que la fecha de inicio", None, None

    return True, None, valid_from, valid_until


@promotions_bp.get("/promotions")
@jwt_required
def get_all_promotions():
    """
    Obtiene todas las promociones con计算ado de estado.

    Query params:
        - status: filter by status (active, inactive, draft, expired, all)
        - search: search in name, description
        - type: filter by promotion_type

    Returns: Lista de promociones con estado calculado
    """
    try:
        status_filter = request.args.get("status", "all")
        search_filter = request.args.get("search", "").lower()
        type_filter = request.args.get("type", "all")

        with get_session() as db:
            query = db.query(Promotion).order_by(Promotion.created_at.desc())

            if type_filter != "all":
                query = query.filter(Promotion.promotion_type == type_filter)

            promotions = query.all()

            datetime.utcnow()
            excluded_count = {"draft": 0, "expired": 0}
            visible_count = {"total": 0, "active": 0, "inactive": 0}

            data = []
            for promo in promotions:
                promo_status = calculate_promotion_status(
                    promo.valid_from, promo.valid_until, promo.is_active
                )

                if status_filter not in ("all", promo_status):
                    excluded_count[
                        promo_status if promo_status in excluded_count else "inactive"
                    ] += 1
                    continue

                if search_filter:
                    name_match = search_filter in promo.name.lower()
                    desc_match = promo.description and search_filter in promo.description.lower()
                    if not name_match and not desc_match:
                        continue

                promo_data = {
                    "id": promo.id,
                    "name": promo.name,
                    "description": promo.description,
                    "promotion_type": promo.promotion_type,
                    "discount_value": float(promo.discount_percentage)
                    if promo.discount_percentage
                    else None,
                    "discount_amount": float(promo.discount_amount)
                    if promo.discount_amount
                    else None,
                    "discount_percentage": float(promo.discount_percentage)
                    if promo.discount_percentage
                    else None,
                    "min_purchase_amount": float(promo.min_purchase_amount)
                    if promo.min_purchase_amount
                    else None,
                    "applies_to": promo.applies_to,
                    "start_date": promo.valid_from.isoformat() if promo.valid_from else None,
                    "end_date": promo.valid_until.isoformat() if promo.valid_until else None,
                    "is_active": promo.is_active,
                    "status": promo_status,
                    "banner_message": promo.banner_message,
                    "created_at": promo.created_at.isoformat(),
                    "tags": parse_json_field(promo.applicable_tags),
                    "products": parse_json_field(promo.applicable_products),
                    "package_name": promo.banner_message if promo.applies_to == "package" else None,
                    "products_count": len(parse_json_field(promo.applicable_products) or []),
                    "tags_count": len(parse_json_field(promo.applicable_tags) or []),
                }
                data.append(promo_data)
                visible_count["total"] += 1
                visible_count[promo_status] += 1

            logger.info(
                f"[PROMOTIONS] Retrieved {len(data)} promotions. "
                f"Visible: {visible_count}. Excluded by status: {excluded_count}"
            )

            return jsonify(
                success_response(
                    {
                        "promotions": data,
                        "stats": {
                            "total": visible_count["total"],
                            "active": visible_count["active"],
                            "inactive": visible_count["inactive"],
                            "draft": sum(1 for p in data if p["status"] == "draft"),
                            "expired": sum(1 for p in data if p["status"] == "expired"),
                        },
                    }
                )
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching promotions: {e}")
        return jsonify(
            success_response(
                {
                    "promotions": [],
                    "stats": {"total": 0, "active": 0, "inactive": 0, "draft": 0, "expired": 0},
                }
            )
        ), HTTPStatus.OK


@promotions_bp.post("/promotions")
@admin_required
def create_promotion():
    """
    Crea una nueva promoción con validación completa.

    Body (requerido):
        - name: str - Nombre de la promoción
        - promotion_type: str - 'percentage', 'fixed' o 'bogo'
        - start_date: str ISO - Fecha de inicio (obligatorio)
        - end_date: str ISO - Fecha de fin (obligatorio)
        - discount_percentage: float (requerido si type es 'percentage')
        - discount_amount: float (requerido si type es 'fixed')
        - applies_to: str - 'all', 'products', 'tags', 'package'
        - is_active: bool (default: true)

    Returns: La promoción creada o error 400
    """
    try:
        data = request.get_json()

        is_valid, error_msg = validate_promotion_data(data)
        if not is_valid:
            logger.warning(f"[PROMOTIONS] Validation failed: {error_msg}")
            return jsonify(error_response(error_msg)), HTTPStatus.BAD_REQUEST

        is_valid, error_msg, valid_from, valid_until = validate_promotion_dates(data)
        if not is_valid:
            logger.warning(f"[PROMOTIONS] Date validation failed: {error_msg}")
            return jsonify(error_response(error_msg)), HTTPStatus.BAD_REQUEST

        is_active = data.get("is_active", True)

        if data["promotion_type"] == "percentage" and not data.get("discount_percentage"):
            return jsonify(
                error_response("discount_percentage es requerido para tipo percentage")
            ), HTTPStatus.BAD_REQUEST
        elif data["promotion_type"] == "fixed" and not data.get("discount_amount"):
            return jsonify(
                error_response("discount_amount es requerido para tipo fixed")
            ), HTTPStatus.BAD_REQUEST

        with get_session() as db:
            promotion = Promotion(
                name=data["name"].strip(),
                description=data.get("description", "").strip() or None,
                promotion_type=data["promotion_type"],
                discount_percentage=data.get("discount_percentage"),
                discount_amount=data.get("discount_amount"),
                min_purchase_amount=data.get("min_purchase_amount"),
                applies_to=data.get("applies_to", "all"),
                applicable_tags=json.dumps(data.get("tags", [])) if data.get("tags") else None,
                applicable_products=json.dumps(data.get("products", []))
                if data.get("products")
                else None,
                valid_from=valid_from,
                valid_until=valid_until,
                is_active=is_active,
                banner_message=data.get("banner_message", "").strip() or None,
            )

            db.add(promotion)
            db.commit()
            db.refresh(promotion)

            promo_status = calculate_promotion_status(valid_from, valid_until, is_active)

            logger.info(
                f"[PROMOTIONS] Created promotion id={promotion.id}, "
                f"name='{promotion.name}', status='{promo_status}'"
            )

            return jsonify(
                success_response(
                    {
                        "promotion": {
                            "id": promotion.id,
                            "name": promotion.name,
                            "description": promotion.description,
                            "promotion_type": promotion.promotion_type,
                            "discount_value": float(promotion.discount_percentage)
                            if promotion.discount_percentage
                            else None,
                            "start_date": promotion.valid_from.isoformat(),
                            "end_date": promotion.valid_until.isoformat()
                            if promotion.valid_until
                            else None,
                            "is_active": promotion.is_active,
                            "status": promo_status,
                            "applies_to": promotion.applies_to,
                        }
                    }
                )
            ), HTTPStatus.CREATED

    except ValueError as e:
        logger.error(f"[PROMOTIONS] Date parsing error: {e}")
        return jsonify(error_response(f"Formato de fecha inválido: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"[PROMOTIONS] Error creating promotion: {e}")
        return jsonify(error_response("Error al crear promoción")), HTTPStatus.INTERNAL_SERVER_ERROR


@promotions_bp.patch("/promotions/<int:promo_id>")
@admin_required
def update_promotion(promo_id: int):
    """Actualiza una promoción existente con validación completa."""
    try:
        data = request.get_json()
        if not data:
            return jsonify(
                error_response("No se proporcionaron datos para actualizar")
            ), HTTPStatus.BAD_REQUEST

        is_valid, error_msg = validate_promotion_data(data)
        if not is_valid and any(
            k in data for k in ["name", "promotion_type", "discount_percentage", "discount_amount"]
        ):
            logger.warning(f"[PROMOTIONS] Update validation failed: {error_msg}")
            return jsonify(error_response(error_msg)), HTTPStatus.BAD_REQUEST

        with get_session() as db:
            promotion = db.query(Promotion).filter(Promotion.id == promo_id).first()
            if not promotion:
                return jsonify(error_response("Promoción no encontrada")), HTTPStatus.NOT_FOUND

            changes = []

            if "name" in data:
                if not data["name"] or not data["name"].strip():
                    return jsonify(
                        error_response("El nombre no puede estar vacío")
                    ), HTTPStatus.BAD_REQUEST
                promotion.name = data["name"].strip()
                changes.append("name")

            if "description" in data:
                promotion.description = data.get("description", "").strip() or None
                changes.append("description")

            if "promotion_type" in data:
                if data["promotion_type"] not in PROMOTION_TYPES:
                    return jsonify(
                        error_response("Tipo de promoción inválido")
                    ), HTTPStatus.BAD_REQUEST
                promotion.promotion_type = data["promotion_type"]
                changes.append("promotion_type")

            if "discount_percentage" in data:
                promotion.discount_percentage = data["discount_percentage"]
                changes.append("discount_percentage")

            if "discount_amount" in data:
                promotion.discount_amount = data["discount_amount"]
                changes.append("discount_amount")

            if "min_purchase_amount" in data:
                promotion.min_purchase_amount = data["min_purchase_amount"]
                changes.append("min_purchase_amount")

            if "applies_to" in data:
                if data["applies_to"] not in APPLIES_TO:
                    return jsonify(error_response("applies_to inválido")), HTTPStatus.BAD_REQUEST
                promotion.applies_to = data["applies_to"]
                changes.append("applies_to")

            if "start_date" in data or "end_date" in data:
                valid_from = promotion.valid_from
                valid_until = promotion.valid_until

                if "start_date" in data:
                    try:
                        valid_from = datetime.fromisoformat(
                            data["start_date"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        return jsonify(
                            error_response("Formato de start_date inválido")
                        ), HTTPStatus.BAD_REQUEST

                if "end_date" in data:
                    try:
                        valid_until = (
                            datetime.fromisoformat(data["end_date"].replace("Z", "+00:00"))
                            if data["end_date"]
                            else None
                        )
                    except (ValueError, TypeError):
                        return jsonify(
                            error_response("Formato de end_date inválido")
                        ), HTTPStatus.BAD_REQUEST

                if valid_until and valid_until <= valid_from:
                    return jsonify(
                        error_response("end_date debe ser mayor que start_date")
                    ), HTTPStatus.BAD_REQUEST

                promotion.valid_from = valid_from
                promotion.valid_until = valid_until
                changes.extend(["valid_from", "valid_until"])

            if "is_active" in data:
                promotion.is_active = bool(data["is_active"])
                changes.append("is_active")

            if "banner_message" in data:
                promotion.banner_message = data.get("banner_message", "").strip() or None
                changes.append("banner_message")

            if "tags" in data:
                promotion.applicable_tags = json.dumps(data["tags"]) if data["tags"] else None
                changes.append("tags")

            if "products" in data:
                promotion.applicable_products = (
                    json.dumps(data["products"]) if data["products"] else None
                )
                changes.append("products")

            db.commit()
            db.refresh(promotion)

            promo_status = calculate_promotion_status(
                promotion.valid_from, promotion.valid_until, promotion.is_active
            )

            logger.info(
                f"[PROMOTIONS] Updated promotion id={promotion.id}, "
                f"changes={changes}, status='{promo_status}'"
            )

            return jsonify(
                success_response(
                    {
                        "promotion": {
                            "id": promotion.id,
                            "name": promotion.name,
                            "is_active": promotion.is_active,
                            "status": promo_status,
                            "changes": changes,
                        }
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        logger.error(f"[PROMOTIONS] Update date error: {e}")
        return jsonify(error_response(f"Formato de fecha inválido: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"[PROMOTIONS] Error updating promotion: {e}")
        return jsonify(
            error_response("Error al actualizar promoción")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@promotions_bp.delete("/promotions/<int:promo_id>")
@admin_required
def delete_promotion(promo_id: int):
    """Elimina una promoción permanentemente."""
    try:
        with get_session() as db:
            promotion = db.query(Promotion).filter(Promotion.id == promo_id).first()
            if not promotion:
                return jsonify(error_response("Promoción no encontrada")), HTTPStatus.NOT_FOUND

            promo_name = promotion.name
            db.delete(promotion)
            db.commit()

            logger.info(f"[PROMOTIONS] Deleted promotion id={promo_id}, name='{promo_name}'")

            return jsonify(
                success_response({"message": "Promoción eliminada correctamente", "id": promo_id})
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"[PROMOTIONS] Error deleting promotion: {e}")
        return jsonify(
            error_response("Error al eliminar promoción")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
