"""Menu read API for client host."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint

menu_bp = Blueprint("client_menu_api", __name__)


@menu_bp.get("/menu")
def get_menu() -> tuple[dict, int]:
    from pronto_shared.services.menu_service import list_menu

    return list_menu(), HTTPStatus.OK
