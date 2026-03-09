"""
Menu endpoints for clients API - BFF CACHE.

This module provides cached menu data for the client app.
Menu is read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

from flask import Blueprint

from ._upstream import forward_to_api

menu_bp = Blueprint("client_menu", __name__)


@menu_bp.get("/menu")
def get_menu():
    """
    Get menu for client app.

    BFF CACHE: Menu is read from pronto-api and cached.
    """
    return forward_to_api("GET", "/api/menu")


@menu_bp.get("/menu/categories")
def get_menu_categories():
    """PROXY: Get menu categories - cached."""
    return forward_to_api("GET", "/api/menu/categories")


@menu_bp.get("/menu/items")
def get_menu_items():
    """PROXY: Get menu items - cached."""
    return forward_to_api("GET", "/api/menu/items")
