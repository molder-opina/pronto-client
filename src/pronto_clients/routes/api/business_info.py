"""
Business info endpoint for clients - BFF PROXY.

Public read-only endpoint used by the customer-facing UI to render
business hours even before authentication. This preserves the business
rule that menu/hours are visible for guests, while order placement
remains authenticated.

Forwarded to pronto-api.
"""

from __future__ import annotations

from typing import Any
from flask import Blueprint

from pronto_shared.trazabilidad import get_logger
from ._upstream import forward_to_api

logger = get_logger(__name__)

business_info_bp = Blueprint("client_business_info", __name__)


@business_info_bp.get("/business-info")
def get_business_info() -> Any:
    """
    Get business information and schedule for client-facing display.

    Public endpoint: does not require customer authentication.
    Proxies to pronto-api.
    """
    return forward_to_api("GET", "/api/business-info")
