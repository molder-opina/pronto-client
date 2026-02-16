"""Public config endpoints for the client-facing app."""

from __future__ import annotations

import os
from http import HTTPStatus

from flask import Blueprint, current_app

from pronto_shared.serializers import success_response
from pronto_shared.services.business_config_service import get_config_value

config_bp = Blueprint("client_config_api", __name__)


def _build_restaurant_assets_path() -> str:
    base_url = (current_app.config.get("PRONTO_STATIC_PUBLIC_HOST") or "").rstrip("/")
    assets_path = (os.getenv("STATIC_ASSETS_PATH") or "/assets").strip("/")
    restaurant_slug = (current_app.config.get("RESTAURANT_SLUG") or "pronto").strip("/") or "pronto"

    if not base_url:
        return f"/{assets_path}/{restaurant_slug}"
    return f"{base_url}/{assets_path}/{restaurant_slug}"


def _safe_config_value(key: str, default):
    try:
        return get_config_value(key, default)
    except Exception as exc:
        current_app.logger.warning("Error reading config key '%s': %s", key, exc)
        return default


@config_bp.get("/config/store_cancel_reason")
def store_cancel_reason() -> tuple[dict, int]:
    value = _safe_config_value("store_cancel_reason", "customer_request")
    return success_response({"value": value}), HTTPStatus.OK


@config_bp.get("/config/client_session_validation_interval_minutes")
def client_session_validation_interval_minutes() -> tuple[dict, int]:
    value = _safe_config_value("client_session_validation_interval_minutes", 5)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 5
    return success_response({"value": value}), HTTPStatus.OK


@config_bp.get("/config/public")
def get_public_config() -> tuple[dict, int]:
    tax_rate = _safe_config_value("tax_rate", current_app.config.get("TAX_RATE", 0.16))
    try:
        tax_rate = float(tax_rate)
    except (TypeError, ValueError):
        tax_rate = 0.16

    payload = {
        "restaurant_name": _safe_config_value(
            "RESTAURANT_NAME",
            current_app.config.get("RESTAURANT_NAME", "Pronto"),
        ),
        "restaurant_assets": _build_restaurant_assets_path(),
        "currency_symbol": _safe_config_value("currency_symbol", "$"),
        "currency_code": _safe_config_value("currency_code", "MXN"),
        "tax_rate": tax_rate,
    }
    return success_response(payload), HTTPStatus.OK
