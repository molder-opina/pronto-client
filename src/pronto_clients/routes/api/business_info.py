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
from zoneinfo import ZoneInfo
from typing import Any

import requests as http_requests

from flask import Blueprint, jsonify

from pronto_shared.trazabilidad import get_logger
from pronto_shared.serializers import success_response
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

business_info_bp = Blueprint("client_business_info", __name__)


def _forward_to_api(path: str) -> tuple[Any, int]:
    """
    Forward request to pronto-api for business info.
    
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


@business_info_bp.get("/business-info")
def get_business_info() -> tuple[Any, int]:
    """
    Get business information and schedule for client-facing display.
    
    BFF CACHE: Business info is read from pronto-api and cached.
    """
    business_info_path = "/api/public/business-info"
    schedule_path = "/api/public/schedule"
    
    # Get business info
    business_info = {}
    try:
        business_info_response, status = _forward_to_api(business_info_path)
        if status == HTTPStatus.OK:
            business_info = (business_info_response.get("data", {})
                            if isinstance(business_info_response, dict) else {})
    except Exception:
        business_info = {}
    
    # Get schedule
    schedule = []
    try:
        schedule_response, status = _forward_to_api(schedule_path)
        if status == HTTPStatus.OK:
            schedule = ((schedule_response.get("data", {}) or {}).get("schedules", [])
                      if isinstance(schedule_response, dict) else [])
    except Exception:
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
