"""
Notifications endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api/src/api_app/routes/notifications.py
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: This is now a BFF proxy to pronto-api. All business logic has been migrated.
"""

from __future__ import annotations

from flask import Blueprint

from ._upstream import forward_to_api

notifications_bp = Blueprint("client_notifications", __name__)


@notifications_bp.get("/notifications")
def get_notifications():
    """PROXY: Get unread notifications for the current authenticated customer."""
    return forward_to_api("GET", "/api/notifications")


@notifications_bp.post("/notifications/<int:notification>/read")
def mark_notification_read(notification: int):
    """PROXY: Mark a notification as read."""
    path = f"/api/notifications/{notification}/read"
    return forward_to_api("POST", path)
