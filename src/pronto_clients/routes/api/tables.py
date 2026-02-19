"""Client Tables API."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint
from pronto_shared.services.table_service import TableService

tables_bp = Blueprint("client_tables_api", __name__)


@tables_bp.get("/tables")
def list_tables() -> tuple[dict, int]:
    """List all available tables (public)."""
    return TableService.list_tables(), HTTPStatus.OK
