"""
API endpoints for waiter table assignments and transfers.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request

from shared.jwt_middleware import get_employee_id, jwt_required
from shared.logging_config import get_logger
from shared.services.waiter_table_assignment_service import (
    accept_transfer_request,
    assign_tables_to_waiter,
    check_table_assignment_conflicts,
    create_transfer_request,
    get_pending_transfer_requests,
    get_table_assignment,
    get_waiter_assigned_tables,
    reject_transfer_request,
    unassign_table_from_waiter,
)

logger = get_logger(__name__)

table_assignments_bp = Blueprint("table_assignments", __name__)


def get_current_employee_id():
    """Get the current employee ID from the session."""
    return get_employee_id()


@table_assignments_bp.route("/table-assignments/my-tables", methods=["GET"])
@jwt_required
def get_my_tables():
    """
    Get all tables assigned to the current waiter.

    Returns:
        200: List of assigned tables
        401: Not authenticated
    """
    waiter_id = get_current_employee_id()
    tables = get_waiter_assigned_tables(waiter_id)

    return jsonify({"tables": tables}), HTTPStatus.OK


@table_assignments_bp.route("/table-assignments/table/<int:table_id>", methods=["GET"])
@jwt_required
def get_table_info(table_id):
    """
    Check if a table is assigned to a waiter.

    Args:
        table_id: ID of the table

    Returns:
        200: Assignment info or null if unassigned
        401: Not authenticated
    """
    assignment = get_table_assignment(table_id)

    return jsonify({"assignment": assignment}), HTTPStatus.OK


@table_assignments_bp.route("/table-assignments/check-conflicts", methods=["POST"])
@jwt_required
def check_conflicts():
    """
    Check for conflicts before assigning tables.

    Request body:
        {
            "table_ids": [1, 2, 3]
        }

    Returns:
        200: List of conflicts with waiter information
        400: Invalid request
        401: Not authenticated
    """
    waiter_id = get_current_employee_id()
    data = request.get_json()

    if not data or "table_ids" not in data:
        return jsonify({"error": "table_ids requerido"}), HTTPStatus.BAD_REQUEST

    table_ids = data["table_ids"]
    if not isinstance(table_ids, list) or not table_ids:
        return jsonify({"error": "table_ids debe ser una lista no vacía"}), HTTPStatus.BAD_REQUEST

    conflicts = check_table_assignment_conflicts(waiter_id, table_ids)

    return jsonify({"conflicts": conflicts}), HTTPStatus.OK


@table_assignments_bp.route("/table-assignments/assign", methods=["POST"])
@jwt_required
def assign_tables():
    """
    Assign multiple tables to the current waiter.

    Request body:
        {
            "table_ids": [1, 2, 3],
            "force": false  # If true, unassign from other waiters
        }

    Returns:
        200: Assignment result with lists of assigned/already_assigned/conflicts
        400: Invalid request
        401: Not authenticated
    """
    waiter_id = get_current_employee_id()
    data = request.get_json()

    if not data or "table_ids" not in data:
        return jsonify({"error": "table_ids requerido"}), HTTPStatus.BAD_REQUEST

    table_ids = data["table_ids"]
    if not isinstance(table_ids, list) or not table_ids:
        return jsonify({"error": "table_ids debe ser una lista no vacía"}), HTTPStatus.BAD_REQUEST

    force = data.get("force", False)
    result, status = assign_tables_to_waiter(waiter_id, table_ids, force=force)

    return jsonify(result), status


@table_assignments_bp.route("/table-assignments/unassign/<int:table_id>", methods=["DELETE"])
@jwt_required
def unassign_table(table_id):
    """
    Unassign a table from the current waiter.

    Args:
        table_id: ID of the table to unassign

    Returns:
        200: Success
        404: Assignment not found
        401: Not authenticated
    """
    waiter_id = get_current_employee_id()
    result, status = unassign_table_from_waiter(waiter_id, table_id)

    return jsonify(result), status


@table_assignments_bp.route("/table-assignments/transfer-requests", methods=["GET"])
@jwt_required
def get_transfer_requests():
    """
    Get all pending transfer requests for the current waiter (incoming).

    Returns:
        200: List of pending transfer requests
        401: Not authenticated
    """
    waiter_id = get_current_employee_id()
    requests = get_pending_transfer_requests(waiter_id)

    return jsonify({"requests": requests}), HTTPStatus.OK


@table_assignments_bp.route("/table-assignments/transfer-request", methods=["POST"])
@jwt_required
def create_transfer():
    """
    Create a table transfer request to another waiter.

    Request body:
        {
            "table_id": 1,
            "to_waiter_id": 5,
            "message": "Optional message"
        }

    Returns:
        201: Transfer request created
        400: Invalid request
        401: Not authenticated
        403: Table not assigned to current waiter
        404: Target waiter not found
        409: Pending request already exists
    """
    from_waiter_id = get_current_employee_id()
    data = request.get_json()

    if not data or "table_id" not in data or "to_waiter_id" not in data:
        return jsonify({"error": "table_id y to_waiter_id requeridos"}), HTTPStatus.BAD_REQUEST

    table_id = data["table_id"]
    to_waiter_id = data["to_waiter_id"]
    message = data.get("message")

    result, status = create_transfer_request(from_waiter_id, to_waiter_id, table_id, message)

    return jsonify(result), status


@table_assignments_bp.route(
    "/table-assignments/transfer-request/<int:request_id>/accept", methods=["POST"]
)
@jwt_required
def accept_transfer(request_id):
    """
    Accept a table transfer request.

    Args:
        request_id: ID of the transfer request

    Request body:
        {
            "transfer_orders": true/false
        }

    Returns:
        200: Transfer accepted
        400: Invalid request
        401: Not authenticated
        403: Not the target waiter
        404: Request not found
        409: Request already resolved
    """
    accepting_waiter_id = get_current_employee_id()
    data = request.get_json()

    if not data or "transfer_orders" not in data:
        return jsonify({"error": "transfer_orders requerido"}), HTTPStatus.BAD_REQUEST

    transfer_orders = bool(data["transfer_orders"])

    result, status = accept_transfer_request(request_id, accepting_waiter_id, transfer_orders)

    return jsonify(result), status


@table_assignments_bp.route(
    "/table-assignments/transfer-request/<int:request_id>/reject", methods=["POST"]
)
@jwt_required
def reject_transfer(request_id):
    """
    Reject a table transfer request.

    Args:
        request_id: ID of the transfer request

    Returns:
        200: Transfer rejected
        401: Not authenticated
        403: Not the target waiter
        404: Request not found
        409: Request already resolved
    """
    rejecting_waiter_id = get_current_employee_id()

    result, status = reject_transfer_request(request_id, rejecting_waiter_id)

    return jsonify(result), status
