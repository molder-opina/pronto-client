"""
Menu endpoints for clients API - BFF CACHE.

This module provides cached menu data for the client app.
Menu is read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

import requests as http_requests
from http import HTTPStatus

from flask import Blueprint

from pronto_shared.serializers import success_response
from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

menu_bp = Blueprint("client_menu", __name__)


def _forward_to_api(path: str):
    """
    Forward request to pronto-api for menu data.
    
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


@menu_bp.get("/menu")
def get_menu():
    """
    Get menu for client app.
    
    BFF CACHE: Menu is read from pronto-api and cached.
    """
    path = "/api/menu"
    data, status = _forward_to_api(path)
    return data, status


@menu_bp.get("/menu/categories")
def get_menu_categories():
    """PROXY: Get menu categories - cached."""
    path = "/api/menu/categories"
    data, status = _forward_to_api(path)
    return data, status


@menu_bp.get("/menu/items")
def get_menu_items():
    """PROXY: Get menu items - cached."""
    path = "/api/menu/items"
    data, status = _forward_to_api(path)
    return data, status
