"""
Keyboard shortcuts endpoints for clients - UI-ONLY.
This module provides keyboard shortcuts metadata for the client UI.
No business logic, no database operations, just static metadata.
This is a frontend convenience endpoint.
Reference: AGENTS.md section 12.4.2
"""
from __future__ import annotations
from flask import Blueprint, jsonify
from http import HTTPStatus
shortcuts_bp = Blueprint("client_shortcuts", __name__)
@shortcuts_bp.get("/shortcuts")
def get_shortcuts():
    """
    Get keyboard shortcuts for the client app.
    
    UI-ONLY endpoint: Returns static metadata without business logic.
    """
    shortcuts = {
        "ctrl+s": {"action": "save", "description": "Guardar orden"},
        "ctrl+e": {"action": "edit", "description": "Editar ítem"},
        "ctrl+d": {"action": "delete", "description": "Eliminar ítem"},
        "ctrl+enter": {"action": "submit", "description": "Enviar orden"},
        "esc": {"action": "close", "description": "Cerrar modal"},
        "f2": {"action": "help", "description": "Mostrar ayuda"},
    }
    
    return jsonify({"shortcuts": shortcuts}), HTTPStatus.OK
