"""
Tables endpoints for clients API - BFF CACHE.

This module provides cached table data for the client app.
Tables are read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint

from ._upstream import forward_to_api

tables_bp = Blueprint("client_tables", __name__)


@tables_bp.get("/tables")
def get_tables():
    """
    Get tables for client app.

    BFF CACHE: Tables are read from pronto-api and cached.
    """
    return forward_to_api("GET", "/api/tables")


@tables_bp.get("/tables/<uuid:table_id>")
def get_table(table_id: UUID):
    """PROXY: Get table details - cached."""
    path = f"/api/tables/{table_id}"
    return forward_to_api("GET", path)
