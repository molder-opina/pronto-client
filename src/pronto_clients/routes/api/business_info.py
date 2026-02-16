"""
Business info endpoint for clients API.
"""

from datetime import datetime
from http import HTTPStatus
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify

business_info_bp = Blueprint("client_business_info", __name__)


@business_info_bp.get("/business-info")
def get_business_info():
    """Get business information and schedule for client-facing display."""
    from pronto_shared.services.business_info_service import BusinessInfoService, BusinessScheduleService

    business_info_response = BusinessInfoService.get_business_info()
    business_info = (
        business_info_response.get("data", {})
        if isinstance(business_info_response, dict)
        else {}
    )

    schedule_response = BusinessScheduleService.get_schedule()
    schedule = (
        (schedule_response.get("data", {}) or {}).get("schedules", [])
        if isinstance(schedule_response, dict)
        else []
    )

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
                    # Use < for close_time to exclude exact closing time
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
