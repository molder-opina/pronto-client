"""
Business info endpoint for clients - BFF CACHE.

This module provides cached business information for the client app.
Business info is read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, session

from pronto_shared.serializers import error_response
from pronto_shared.services.business_info_service import BusinessInfoService, BusinessScheduleService
from pronto_shared.services.customer_session_store import RedisUnavailableError, customer_session_store
from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

business_info_bp = Blueprint("client_business_info", __name__)


def _require_authenticated_customer() -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return None, (error_response("Autenticación requerida"), HTTPStatus.UNAUTHORIZED)

    try:
        customer = customer_session_store.get_customer(customer_ref)
    except RedisUnavailableError:
        logger.warning("Customer session store unavailable while resolving business info")
        return None, (
            error_response("No se pudo validar la sesión del cliente"),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Unexpected error resolving business info customer session",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return None, (
            error_response("No se pudo validar la sesión del cliente"),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    if not customer:
        return None, (error_response("Autenticación requerida"), HTTPStatus.UNAUTHORIZED)

    return customer, None


@business_info_bp.get("/business-info")
def get_business_info() -> tuple[Any, int]:
    """
    Get business information and schedule for client-facing display.

    This route requires an authenticated customer session and reads the canonical
    shared services instead of depending on deprecated public API surfaces.
    """
    _customer, auth_error = _require_authenticated_customer()
    if auth_error:
        return auth_error
    
    business_info = {}
    try:
        business_info_response = BusinessInfoService.get_business_info()
        if business_info_response.get("status") == "success":
            business_info = business_info_response.get("data") or {}
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Error loading business info for client API",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        business_info = {}

    schedule = []
    try:
        schedule_response = BusinessScheduleService.get_schedule()
        if schedule_response.get("status") == "success":
            schedule = (schedule_response.get("data") or {}).get("schedules", [])
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Error loading business schedule for client API",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        schedule = []

    tz_name = (business_info or {}).get("timezone") or "America/Mexico_City"
    try:
        tzinfo = ZoneInfo(tz_name)
    except Exception:
        tzinfo = ZoneInfo("America/Mexico_City")
    
    now = datetime.now(tzinfo)
    current_day = now.weekday()
    current_time = now.strftime("%H:%M")
    
    current_day_schedule = None
    is_currently_open = False

    for day_schedule in schedule:
        if day_schedule["day_of_week"] == current_day:
            current_day_schedule = day_schedule

            if day_schedule["is_open"]:
                open_time = day_schedule["open_time"]
                close_time = day_schedule["close_time"]

                if open_time and close_time:
                    is_currently_open = open_time <= current_time < close_time

            break

    return jsonify(
        {
            "business_name": business_info.get("business_name", "Restaurant"),
            "schedule": schedule,
            "is_currently_open": is_currently_open,
            "current_day_schedule": current_day_schedule,
        }
    ), HTTPStatus.OK
