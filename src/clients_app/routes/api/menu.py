"""
Menu endpoint for clients API.
"""

from flask import Blueprint, jsonify

from clients_app.services.menu_service import fetch_menu

menu_bp = Blueprint("client_menu", __name__)


@menu_bp.get("/menu")
def get_menu():
    """Return the list of menu categories and items."""
    return jsonify(fetch_menu())
