"""
Split bill endpoints for clients API - BFF PROXY TO PRONTO-API.

# DEPRECATED: Este módulo implementa lógica de negocio que debe vivir en pronto-api.
# Fecha de sunset: TBD (por definir en roadmap)
# Motivo: pronto-client no debe implementar endpoints de negocio según AGENTS.md sección 12.4.2.
# Autoridad única de API: pronto-api en :6082 bajo "/api/*".
# Plan de retiro: Migrar lógica de negocio a pronto-api/src/api_app/routes/customers/split_bills.py
# Referencia: AGENTS.md sección 12.4.2, 12.4.3, 12.4.4

NOTE: This is now a BFF proxy to pronto-api. All business logic has been migrated.
"""

from __future__ import annotations

import requests as http_requests
from http import HTTPStatus
from uuid import UUID

from flask import Blueprint, jsonify, request

from pronto_shared.trazabilidad import get_logger
from ._upstream import get_pronto_api_base_url

logger = get_logger(__name__)

split_bills_bp = Blueprint("client_split_bills", __name__)


def _forward_to_api(method: str, path: str, data: dict | None = None):
    """
    Forward request to pronto-api.
    
    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    No business logic is applied here.
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    
    headers = {
        "X-PRONTO-CUSTOMER-REF": request.headers.get("X-PRONTO-CUSTOMER-REF", ""),
        "Content-Type": "application/json",
    }
    
    # Forward correlation ID if present
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    csrf_token = request.headers.get("X-CSRFToken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    
    try:
        if method == "GET":
            response = http_requests.get(url, headers=headers, cookies=request.cookies, timeout=5)
        elif method == "POST":
            response = http_requests.post(url, json=data, headers=headers, cookies=request.cookies, timeout=5)
        else:
            return jsonify({"error": "Method not supported"}), HTTPStatus.METHOD_NOT_ALLOWED
        
        # Return response from pronto-api
        return jsonify(response.json()), response.status_code
    
    except http_requests.Timeout:
        return jsonify({"error": "Timeout conectando a API"}), HTTPStatus.GATEWAY_TIMEOUT
    except http_requests.RequestException as e:
        logger.error(f"Error forwarding to pronto-api: {e}", error={"exception": str(e)})
        return jsonify({"error": "Error conectando a API"}), HTTPStatus.BAD_GATEWAY


@split_bills_bp.post("/sessions/<uuid:session_id>/split-bill")
def create_split_bill(session_id: UUID):
    """PROXY: Create a split bill for a dining session."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/sessions/{session_id}/split-bill"
    return _forward_to_api("POST", path, data=payload)


@split_bills_bp.get("/split-bills/<uuid:split_id>")
def get_split_bill(split_id: UUID):
    """PROXY: Get split bill details."""
    path = f"/api/customers/split-bills/split-bills/{split_id}"
    return _forward_to_api("GET", path)


@split_bills_bp.post("/split-bills/<uuid:split_id>/assign")
def assign_item_to_person(split_id: UUID):
    """PROXY: Assign an order item to a person in the split."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/split-bills/{split_id}/assign"
    return _forward_to_api("POST", path, data=payload)


@split_bills_bp.post("/split-bills/<uuid:split_id>/calculate")
def calculate_split_totals(split_id: UUID):
    """PROXY: Recalculate totals for all people in the split."""
    path = f"/api/customers/split-bills/split-bills/{split_id}/calculate"
    return _forward_to_api("POST", path)


@split_bills_bp.get("/split-bills/<uuid:split_id>/summary")
def get_split_summary(split_id: UUID):
    """PROXY: Get a summary of the split."""
    path = f"/api/customers/split-bills/split-bills/{split_id}/summary"
    return _forward_to_api("GET", path)


@split_bills_bp.post("/split-bills/<uuid:split_id>/people/<uuid:person_id>/pay")
def pay_split_person(split_id: UUID, person_id: UUID):
    """PROXY: Process payment for an individual person in a split bill."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/split-bills/{split_id}/people/{person_id}/pay"
    return _forward_to_api("POST", path, data=payload)
