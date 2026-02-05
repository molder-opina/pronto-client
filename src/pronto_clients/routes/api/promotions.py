"""
Promotions and discount codes endpoints for clients API.
"""

from datetime import datetime, timezone
from http import HTTPStatus

from flask import Blueprint, jsonify, request

promotions_bp = Blueprint("client_promotions", __name__)


@promotions_bp.get("/promotions")
def get_promotions():
    # Alias kept for debug panel compatibility.
    return get_active_promotions()


@promotions_bp.get("/promotions/active")
def get_active_promotions():
    """Get active promotions for display."""
    from pronto_shared.db import get_session
    from pronto_shared.models import Promotion

    is_registered = request.args.get("is_registered", "false").lower() == "true"

    with get_session() as db_session:
        now = datetime.now(timezone.utc)
        query = db_session.query(Promotion).filter(
            Promotion.is_active, Promotion.valid_from <= now
        )

        query = query.filter(
            (Promotion.valid_until.is_(None)) | (Promotion.valid_until >= now)
        )

        if is_registered:
            query = query.filter(Promotion.applies_to.in_(["all", "registered"]))
        else:
            query = query.filter(Promotion.applies_to.in_(["all", "anonymous"]))

        promotions = query.all()

        return jsonify(
            {
                "promotions": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "banner_message": p.banner_message,
                        "promotion_type": p.promotion_type,
                        "discount_percentage": float(p.discount_percentage)
                        if p.discount_percentage
                        else None,
                        "discount_amount": float(p.discount_amount)
                        if p.discount_amount
                        else None,
                        "min_purchase_amount": float(p.min_purchase_amount)
                        if p.min_purchase_amount
                        else None,
                    }
                    for p in promotions
                ]
            }
        ), HTTPStatus.OK


@promotions_bp.post("/discount-code/validate")
def validate_discount_code():
    """Validate a discount code."""
    from pronto_shared.db import get_session
    from pronto_shared.models import DiscountCode

    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "").strip().upper()
    is_registered = payload.get("is_registered", False)
    cart_total = payload.get("cart_total", 0)

    if not code:
        return jsonify({"error": "Code is required"}), HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        discount = (
            db_session.query(DiscountCode).filter_by(code=code, is_active=True).first()
        )

        if not discount:
            return jsonify({"error": "Invalid discount code"}), HTTPStatus.NOT_FOUND

        now = datetime.now(timezone.utc)

        if discount.valid_from > now:
            return jsonify(
                {"error": "This code is not yet valid"}
            ), HTTPStatus.BAD_REQUEST

        if discount.valid_until and discount.valid_until < now:
            return jsonify({"error": "This code has expired"}), HTTPStatus.BAD_REQUEST

        if discount.usage_limit and discount.times_used >= discount.usage_limit:
            return jsonify(
                {"error": "This code has reached its usage limit"}
            ), HTTPStatus.BAD_REQUEST

        if discount.applies_to == "registered" and not is_registered:
            return jsonify(
                {"error": "This code is only for registered users"}
            ), HTTPStatus.BAD_REQUEST

        if discount.applies_to == "anonymous" and is_registered:
            return jsonify(
                {"error": "This code is only for new users"}
            ), HTTPStatus.BAD_REQUEST

        if discount.min_purchase_amount and cart_total < float(
            discount.min_purchase_amount
        ):
            return jsonify(
                {
                    "error": f"Compra mínima de ${discount.min_purchase_amount} MXN requerida"
                }
            ), HTTPStatus.BAD_REQUEST

        discount_value = 0
        if discount.discount_type == "percentage":
            discount_value = cart_total * (float(discount.discount_percentage) / 100)
        else:
            discount_value = float(discount.discount_amount)

        return jsonify(
            {
                "status": "ok",
                "code": discount.code,
                "discount_type": discount.discount_type,
                "discount_value": round(discount_value, 2),
                "description": discount.description,
            }
        ), HTTPStatus.OK
