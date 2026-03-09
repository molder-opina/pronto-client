"""
Business info endpoint for clients - BFF CACHE.

Public read-only endpoint used by the customer-facing UI to render
business hours even before authentication. This preserves the business
rule that menu/hours are visible for guests, while order placement
remains authenticated.

Business info is read from shared services.
"""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify

from pronto_shared.services.business_info_service import BusinessInfoService, BusinessScheduleService
from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

business_info_bp = Blueprint("client_business_info", __name__)


@business_info_bp.get("/business-info")
def get_business_info() -> tuple[Any, int]:
    """
    Get business information and schedule for client-facing display.

    Public endpoint: does not require customer authentication.
    """

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
