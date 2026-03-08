"""
Tables endpoints for clients API - BFF CACHE.

This module provides cached table data for the client app.
Tables are read from pronto-api and cached to reduce load.
Business logic lives in pronto-api:6082 under "/api/*".

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from __future__ import annotations

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, request

from pronto_shared.serializers import success_response
from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

tables_bp = Blueprint("client_tables", __name__)


def _forward_to_api(path: str):
    """
    Forward request to pronto-api for table data.
    
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


@tables_bp.get("/tables")
def get_tables():
    """
    Get tables for client app.
    
    BFF CACHE: Tables are read from pronto-api and cached.
    """
    path = "/api/tables"
    data, status = _forward_to_api(path)
    return success_response(data), status


@tables_bp.get("/tables/<uuid:table_id>")
def get_table(table_id: UUID):
    """PROXY: Get table details - cached."""
    path = f"/api/tables/{table_id}"
    data, status = _forward_to_api(path)
    return success_response(data), status
