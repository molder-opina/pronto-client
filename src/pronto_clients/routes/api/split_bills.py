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

from uuid import UUID

from flask import Blueprint, request

from ._upstream import forward_to_api

split_bills_bp = Blueprint("client_split_bills", __name__)


@split_bills_bp.post("/sessions/<uuid:session_id>/split-bill")
def create_split_bill(session_id: UUID):
    """PROXY: Create a split bill for a dining session."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/sessions/{session_id}/split-bill"
    return forward_to_api("POST", path, data=payload)


@split_bills_bp.get("/split-bills/<uuid:split_id>")
def get_split_bill(split_id: UUID):
    """PROXY: Get split bill details."""
    path = f"/api/customers/split-bills/split-bills/{split_id}"
    return forward_to_api("GET", path)


@split_bills_bp.post("/split-bills/<uuid:split_id>/assign")
def assign_item_to_person(split_id: UUID):
    """PROXY: Assign an order item to a person in the split."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/split-bills/{split_id}/assign"
    return forward_to_api("POST", path, data=payload)


@split_bills_bp.post("/split-bills/<uuid:split_id>/calculate")
def calculate_split_totals(split_id: UUID):
    """PROXY: Recalculate totals for all people in the split."""
    path = f"/api/customers/split-bills/split-bills/{split_id}/calculate"
    return forward_to_api("POST", path)


@split_bills_bp.get("/split-bills/<uuid:split_id>/summary")
def get_split_summary(split_id: UUID):
    """PROXY: Get a summary of the split."""
    path = f"/api/customers/split-bills/split-bills/{split_id}/summary"
    return forward_to_api("GET", path)


@split_bills_bp.post("/split-bills/<uuid:split_id>/people/<uuid:person_id>/pay")
def pay_split_person(split_id: UUID, person_id: UUID):
    """PROXY: Process payment for an individual person in a split bill."""
    payload = request.get_json(silent=True) or {}
    path = f"/api/customers/split-bills/split-bills/{split_id}/people/{person_id}/pay"
    return forward_to_api("POST", path, data=payload)
