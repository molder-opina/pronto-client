"""
Service for managing waiter-table assignments and transfers.
Handles shift-persistent table assignments and inter-waiter transfer workflows.
"""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus

from sqlalchemy import and_, select

from shared.constants import OrderStatus
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import (
    Area,
    DiningSession,
    Employee,
    Order,
    Table,
    TableTransferRequest,
    WaiterTableAssignment,
)
from shared.supabase.realtime import emit_custom_event

logger = get_logger(__name__)


def get_waiter_assigned_tables(waiter_id: int) -> list[dict]:
    """
    Get all tables currently assigned to a waiter.

    Returns:
        List of dicts with table info: {id, table_number, area, capacity, ...}
    """
    with get_session() as session:
        stmt = (
            select(WaiterTableAssignment, Table, Area)
            .join(Table, WaiterTableAssignment.table_id == Table.id)
            .join(Area, Table.area_id == Area.id)
            .where(
                and_(
                    WaiterTableAssignment.waiter_id == waiter_id,
                    WaiterTableAssignment.is_active,
                    Table.is_active,
                )
            )
            .order_by(Area.prefix, Area.name, Table.table_number)
        )

        results = session.execute(stmt).all()

        return [
            {
                "id": table.id,
                "table_number": table.table_number,
                "area": {
                    "id": area.id,
                    "prefix": area.prefix,
                    "name": area.name,
                },
                "capacity": table.capacity,
                "status": table.status,
                "assigned_at": assignment.assigned_at.isoformat()
                if assignment.assigned_at
                else None,
            }
            for assignment, table, area in results
        ]


def get_table_assignment(table_id: int) -> dict | None:
    """
    Check if a table is assigned to a waiter.

    Returns:
        Dict with assignment info or None if unassigned
    """
    with get_session() as session:
        stmt = (
            select(WaiterTableAssignment, Employee)
            .join(Employee, WaiterTableAssignment.waiter_id == Employee.id)
            .where(
                and_(WaiterTableAssignment.table_id == table_id, WaiterTableAssignment.is_active)
            )
        )

        result = session.execute(stmt).first()

        if not result:
            return None

        assignment, waiter = result
        return {
            "waiter_id": waiter.id,
            "waiter_name": waiter.name,
            "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        }


def check_table_assignment_conflicts(waiter_id: int, table_ids: list[int]) -> list[dict]:
    """
    Check for conflicts before assigning tables.
    Returns list of tables that are assigned to other waiters.

    Args:
        waiter_id: ID of the waiter trying to assign
        table_ids: List of table IDs to check

    Returns:
        List of conflict dicts with table_id, table_number, current_waiter_id, current_waiter_name
    """
    conflicts = []

    with get_session() as session:
        for table_id in table_ids:
            table = session.get(Table, table_id)
            if not table or not table.is_active:
                continue

            area = session.get(Area, table.area_id) if table.area_id else None

            other_assignment = session.execute(
                select(WaiterTableAssignment, Employee)
                .join(Employee, WaiterTableAssignment.waiter_id == Employee.id)
                .where(
                    and_(
                        WaiterTableAssignment.table_id == table_id,
                        WaiterTableAssignment.is_active,
                        WaiterTableAssignment.waiter_id != waiter_id,
                    )
                )
            ).first()

            if other_assignment:
                _, other_waiter = other_assignment
                conflicts.append(
                    {
                        "table_id": table_id,
                        "table_number": table.table_number,
                        "area": {
                            "id": area.id if area else None,
                            "prefix": area.prefix if area else None,
                            "name": area.name if area else None,
                        },
                        "current_waiter_id": other_waiter.id,
                        "current_waiter_name": other_waiter.name,
                    }
                )

    return conflicts


def assign_tables_to_waiter(
    waiter_id: int, table_ids: list[int], force: bool = False
) -> tuple[dict, HTTPStatus]:
    """
    Assign multiple tables to a waiter.
    Creates new assignments for tables not already assigned to this waiter.

    Args:
        waiter_id: ID of the waiter
        table_ids: List of table IDs to assign
        force: If True, unassign tables from other waiters before assigning

    Returns:
        Tuple of (response_dict, http_status)
    """
    with get_session() as session:
        # Verify waiter exists
        waiter = session.get(Employee, waiter_id)
        if not waiter:
            return {"error": "Mesero no encontrado"}, HTTPStatus.NOT_FOUND

        assigned_tables = []
        already_assigned = []
        conflicts = []

        for table_id in table_ids:
            # Check if table exists and is active
            table = session.get(Table, table_id)
            if not table or not table.is_active:
                conflicts.append({"table_id": table_id, "reason": "Mesa no encontrada o inactiva"})
                continue

            # Check if *any* assignment exists for this waiter (active or inactive)
            # This is necessary because of the unique constraint on (waiter_id, table_id)
            existing_assignment = (
                session.execute(
                    select(WaiterTableAssignment).where(
                        and_(
                            WaiterTableAssignment.waiter_id == waiter_id,
                            WaiterTableAssignment.table_id == table_id,
                        )
                    )
                )
                .scalars()
                .first()
            )

            if existing_assignment:
                if existing_assignment.is_active:
                    already_assigned.append(table.table_number)
                else:
                    # Reactivate existing assignment
                    existing_assignment.is_active = True
                    existing_assignment.assigned_at = datetime.utcnow()
                    existing_assignment.unassigned_at = None
                    assigned_tables.append(table.table_number)
                continue

            # Check if assigned to another waiter (active only)
            other_assignment = session.execute(
                select(WaiterTableAssignment, Employee)
                .join(Employee, WaiterTableAssignment.waiter_id == Employee.id)
                .where(
                    and_(
                        WaiterTableAssignment.table_id == table_id,
                        WaiterTableAssignment.is_active,
                        WaiterTableAssignment.waiter_id != waiter_id,
                    )
                )
            ).first()

            if other_assignment:
                assignment, other_waiter = other_assignment
                if force:
                    # Unassign from other waiter
                    assignment.is_active = False
                    assignment.unassigned_at = datetime.utcnow()
                    # Create new assignment for current waiter
                    new_assignment = WaiterTableAssignment(
                        waiter_id=waiter_id,
                        table_id=table_id,
                        is_active=True,
                        assigned_at=datetime.utcnow(),
                    )
                    session.add(new_assignment)
                    assigned_tables.append(table.table_number)
                else:
                    conflicts.append(
                        {
                            "table_id": table_id,
                            "table_number": table.table_number,
                            "reason": f"Ya asignada a {other_waiter.name}",
                            "current_waiter_id": other_waiter.id,
                            "current_waiter_name": other_waiter.name,
                        }
                    )
                continue

            # Create new assignment
            assignment = WaiterTableAssignment(
                waiter_id=waiter_id,
                table_id=table_id,
                is_active=True,
                assigned_at=datetime.utcnow(),
            )
            session.add(assignment)
            assigned_tables.append(table.table_number)

        session.commit()

        logger.info(f"Waiter {waiter_id} assigned to tables: {assigned_tables}")

        return {
            "assigned": assigned_tables,
            "already_assigned": already_assigned,
            "conflicts": conflicts,
        }, HTTPStatus.OK


def unassign_table_from_waiter(waiter_id: int, table_id: int) -> tuple[dict, HTTPStatus]:
    """
    Unassign a table from a waiter.

    Args:
        waiter_id: ID of the waiter
        table_id: ID of the table to unassign

    Returns:
        Tuple of (response_dict, http_status)
    """
    with get_session() as session:
        assignment = (
            session.execute(
                select(WaiterTableAssignment).where(
                    and_(
                        WaiterTableAssignment.waiter_id == waiter_id,
                        WaiterTableAssignment.table_id == table_id,
                        WaiterTableAssignment.is_active,
                    )
                )
            )
            .scalars()
            .first()
        )

        if not assignment:
            return {"error": "Asignación no encontrada"}, HTTPStatus.NOT_FOUND

        # Mark as inactive
        assignment.is_active = False
        assignment.unassigned_at = datetime.utcnow()
        session.commit()

        logger.info(f"Waiter {waiter_id} unassigned from table {table_id}")

        return {"success": True}, HTTPStatus.OK


def create_transfer_request(
    from_waiter_id: int, to_waiter_id: int, table_id: int, message: str | None = None
) -> tuple[dict, HTTPStatus]:
    """
    Create a table transfer request from one waiter to another.

    Args:
        from_waiter_id: Current waiter (requester)
        to_waiter_id: Target waiter (must accept)
        table_id: Table to transfer
        message: Optional message

    Returns:
        Tuple of (response_dict, http_status)
    """
    with get_session() as session:
        # Verify table is assigned to from_waiter
        assignment = (
            session.execute(
                select(WaiterTableAssignment).where(
                    and_(
                        WaiterTableAssignment.waiter_id == from_waiter_id,
                        WaiterTableAssignment.table_id == table_id,
                        WaiterTableAssignment.is_active,
                    )
                )
            )
            .scalars()
            .first()
        )

        if not assignment:
            return {"error": "La mesa no está asignada a ti"}, HTTPStatus.FORBIDDEN

        # Check if target waiter exists
        to_waiter = session.get(Employee, to_waiter_id)
        if not to_waiter:
            return {"error": "Mesero destino no encontrado"}, HTTPStatus.NOT_FOUND

        # Check for pending transfer request for this table
        pending = (
            session.execute(
                select(TableTransferRequest).where(
                    and_(
                        TableTransferRequest.table_id == table_id,
                        TableTransferRequest.status == "pending",
                    )
                )
            )
            .scalars()
            .first()
        )

        if pending:
            return {
                "error": "Ya existe una solicitud pendiente para esta mesa"
            }, HTTPStatus.CONFLICT

        # Create transfer request
        transfer_request = TableTransferRequest(
            table_id=table_id,
            from_waiter_id=from_waiter_id,
            to_waiter_id=to_waiter_id,
            status="pending",
            transfer_orders=False,  # Will be set by accepting waiter
            message=message,
            created_at=datetime.utcnow(),
        )
        session.add(transfer_request)
        session.commit()
        session.refresh(transfer_request)

        # Emit notification to target waiter
        table = session.get(Table, table_id)
        from_waiter = session.get(Employee, from_waiter_id)

        emit_custom_event(
            "table.transfer_request",
            {
                "transfer_request_id": transfer_request.id,
                "table_id": table_id,
                "table_number": table.table_number if table else None,
                "from_waiter_id": from_waiter_id,
                "from_waiter_name": from_waiter.name if from_waiter else None,
                "message": message,
            },
            room=f"employee_{to_waiter_id}",
        )

        logger.info(
            f"Transfer request created: table {table_id} from waiter {from_waiter_id} to {to_waiter_id}"
        )

        return {"transfer_request_id": transfer_request.id, "status": "pending"}, HTTPStatus.CREATED


def accept_transfer_request(
    transfer_request_id: int, accepting_waiter_id: int, transfer_orders: bool = False
) -> tuple[dict, HTTPStatus]:
    """
    Accept a table transfer request.

    Args:
        transfer_request_id: ID of the transfer request
        accepting_waiter_id: ID of the waiter accepting (must be to_waiter)
        transfer_orders: Whether to transfer existing orders to the new waiter

    Returns:
        Tuple of (response_dict, http_status)
    """
    with get_session() as session:
        transfer_request = session.get(TableTransferRequest, transfer_request_id)

        if not transfer_request:
            return {"error": "Solicitud no encontrada"}, HTTPStatus.NOT_FOUND

        if transfer_request.to_waiter_id != accepting_waiter_id:
            return {"error": "No tienes permiso para aceptar esta solicitud"}, HTTPStatus.FORBIDDEN

        if transfer_request.status != "pending":
            return {"error": "Esta solicitud ya fue resuelta"}, HTTPStatus.CONFLICT

        # Update transfer request
        transfer_request.status = "accepted"
        transfer_request.transfer_orders = transfer_orders
        transfer_request.resolved_at = datetime.utcnow()
        transfer_request.resolved_by_employee_id = accepting_waiter_id

        # Unassign from old waiter
        old_assignment = (
            session.execute(
                select(WaiterTableAssignment).where(
                    and_(
                        WaiterTableAssignment.waiter_id == transfer_request.from_waiter_id,
                        WaiterTableAssignment.table_id == transfer_request.table_id,
                        WaiterTableAssignment.is_active,
                    )
                )
            )
            .scalars()
            .first()
        )

        if old_assignment:
            old_assignment.is_active = False
            old_assignment.unassigned_at = datetime.utcnow()

        # Assign to new waiter
        new_assignment = WaiterTableAssignment(
            waiter_id=accepting_waiter_id,
            table_id=transfer_request.table_id,
            is_active=True,
            assigned_at=datetime.utcnow(),
            notes=f"Transferred from waiter {transfer_request.from_waiter_id}",
        )
        session.add(new_assignment)

        # Transfer orders if requested
        transferred_order_count = 0
        if transfer_orders:
            # Find all active orders for this table
            active_orders = (
                session.execute(
                    select(Order)
                    .join(DiningSession, Order.session_id == DiningSession.id)
                    .where(
                        and_(
                            DiningSession.table_id == transfer_request.table_id,
                            Order.workflow_status.in_(
                                [
                                    OrderStatus.NEW.value,
                                    OrderStatus.QUEUED.value,
                                    OrderStatus.PREPARING.value,
                                    OrderStatus.READY.value,
                                ]
                            ),
                            Order.waiter_id == transfer_request.from_waiter_id,
                        )
                    )
                )
                .scalars()
                .all()
            )

            for order in active_orders:
                order.waiter_id = accepting_waiter_id
                transferred_order_count += 1

        session.commit()

        # Notify old waiter
        emit_custom_event(
            "table.transfer_accepted",
            {
                "transfer_request_id": transfer_request_id,
                "table_id": transfer_request.table_id,
                "new_waiter_id": accepting_waiter_id,
                "orders_transferred": transfer_orders,
                "order_count": transferred_order_count,
            },
            room=f"employee_{transfer_request.from_waiter_id}",
        )

        logger.info(
            f"Transfer accepted: table {transfer_request.table_id} "
            f"from waiter {transfer_request.from_waiter_id} to {accepting_waiter_id} "
            f"(orders transferred: {transfer_orders}, count: {transferred_order_count})"
        )

        return {
            "success": True,
            "orders_transferred": transferred_order_count if transfer_orders else 0,
        }, HTTPStatus.OK


def reject_transfer_request(
    transfer_request_id: int, rejecting_waiter_id: int
) -> tuple[dict, HTTPStatus]:
    """
    Reject a table transfer request.

    Args:
        transfer_request_id: ID of the transfer request
        rejecting_waiter_id: ID of the waiter rejecting (must be to_waiter)

    Returns:
        Tuple of (response_dict, http_status)
    """
    with get_session() as session:
        transfer_request = session.get(TableTransferRequest, transfer_request_id)

        if not transfer_request:
            return {"error": "Solicitud no encontrada"}, HTTPStatus.NOT_FOUND

        if transfer_request.to_waiter_id != rejecting_waiter_id:
            return {"error": "No tienes permiso para rechazar esta solicitud"}, HTTPStatus.FORBIDDEN

        if transfer_request.status != "pending":
            return {"error": "Esta solicitud ya fue resuelta"}, HTTPStatus.CONFLICT

        # Update transfer request
        transfer_request.status = "rejected"
        transfer_request.resolved_at = datetime.utcnow()
        transfer_request.resolved_by_employee_id = rejecting_waiter_id

        session.commit()

        # Notify requesting waiter
        emit_custom_event(
            "table.transfer_rejected",
            {
                "transfer_request_id": transfer_request_id,
                "table_id": transfer_request.table_id,
            },
            room=f"employee_{transfer_request.from_waiter_id}",
        )

        logger.info(
            f"Transfer rejected: request {transfer_request_id} by waiter {rejecting_waiter_id}"
        )

        return {"success": True}, HTTPStatus.OK


def get_pending_transfer_requests(waiter_id: int) -> list[dict]:
    """
    Get all pending transfer requests for a waiter (incoming).

    Args:
        waiter_id: ID of the waiter

    Returns:
        List of pending transfer requests
    """
    with get_session() as session:
        stmt = (
            select(TableTransferRequest, Table, Employee)
            .join(Table, TableTransferRequest.table_id == Table.id)
            .join(Employee, TableTransferRequest.from_waiter_id == Employee.id)
            .where(
                and_(
                    TableTransferRequest.to_waiter_id == waiter_id,
                    TableTransferRequest.status == "pending",
                )
            )
            .order_by(TableTransferRequest.created_at.desc())
        )

        results = session.execute(stmt).all()

        return [
            {
                "id": transfer.id,
                "table_id": table.id,
                "table_number": table.table_number,
                "from_waiter_id": from_waiter.id,
                "from_waiter_name": from_waiter.name,
                "message": transfer.message,
                "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
            }
            for transfer, table, from_waiter in results
        ]
