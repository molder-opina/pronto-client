"""
Public config endpoints for client-facing app - BFF CACHE.
This module provides cached public configuration for the client app.
Configuration is read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".
Reference: AGENTS.md section 12.4.2, 12.4.3
"""
from __future__ import annotations
import os
import requests as http_requests
from http import HTTPStatus
from flask import Blueprint, current_app
from pronto_shared.serializers import success_response
from pronto_shared.services.business_config_service import get_config_value
from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url
logger = get_logger(__name__)
config_bp = Blueprint("client_config_api", __name__)
def _build_restaurant_assets_path() -> str:
    base_url = (current_app.config.get("PRONTO_STATIC_PUBLIC_HOST") or "").rstrip("/")
    assets_path = (os.getenv("STATIC_ASSETS_PATH") or "/assets").strip("/")
    restaurant_slug = (current_app.config.get("RESTAURANT_SLUG") or "pronto").strip("/") or "pronto"
    if not base_url:
        return f"/{assets_path}/{restaurant_slug}"
    return f"{base_url}/{assets_path}/{restaurant_slug}"
def _forward_to_api(path: str) -> tuple[dict, int]:
    """
    Forward request to pronto-api for config data.
    
    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    
    try:
        response = http_requests.get(url, timeout=5)
        return response.json(), response.status_code
    except http_requests.Timeout:
        error = {"error": "Timeout conectando a API"}
        return error, HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        error = {"error": "Error conectando a API"}
        return error, HTTPStatus.BAD_GATEWAY
def _safe_config_value(key: str, default):
    try:
        return get_config_value(key, default)
    except Exception as exc:
        logger.warning("Error reading config key '%s': %s", key, exc, error={"message": str(exc)})
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
@config_bp.get("/public/config")
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
