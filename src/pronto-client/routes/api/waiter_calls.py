"""
Waiter call endpoints for clients API.
"""

from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from pronto_shared.services.waiter_call_service import get_waiter_assignment_from_db
from pronto_shared.supabase.realtime import emit_waiter_call

waiter_calls_bp = Blueprint("client_waiter_calls", __name__)


@waiter_calls_bp.post("/call-waiter")
def call_waiter():
    """
    Register a customer request to call a waiter.
    This creates a WaiterCall record that tracks the status and confirmation.
    """
    from sqlalchemy import and_, select
    from sqlalchemy.orm import joinedload

    from pronto_shared.db import get_session
    from pronto_shared.models import (
        DiningSession,
        Notification,
        Order,
        Table,
        WaiterCall,
        WaiterTableAssignment,
    )

    payload = request.get_json(silent=True) or {}
    table_number = payload.get("table_number", "").strip()
    session_id = payload.get("session_id")

    if not table_number:
        return jsonify({"error": "El número de mesa es requerido"}), HTTPStatus.BAD_REQUEST

    if len(table_number) > 32:
        return jsonify({"error": "Número de mesa inválido"}), HTTPStatus.BAD_REQUEST

    order_numbers = []
    waiter_call_created_at = None
    waiter_id = waiter_name = None
    table_id = None
    table_created_at = None

    with get_session() as session:
        table_obj = (
            session.execute(select(Table).where(Table.table_number == table_number))
            .scalars()
            .one_or_none()
        )

        if not table_obj:
            return jsonify({"error": "Mesa no encontrada"}), HTTPStatus.BAD_REQUEST

        # Store table info before session ends
        table_id = table_obj.id
        table_created_at = table_obj.created_at

        two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

        recent_call = (
            session.execute(
                select(WaiterCall).where(
                    and_(
                        WaiterCall.table_number == table_number,
                        WaiterCall.status == "pending",
                        WaiterCall.created_at >= two_minutes_ago,
                    )
                )
            )
            .scalars()
            .first()
        )

        if recent_call:
            try:
                from pronto_shared.models import DiningSession
                from pronto_shared.services.waiter_call_service import (
                    get_waiter_assignment_from_dining_session,
                )

                waiter_id = None
                waiter_name = None
                if session_id:
                    dining_session = session.get(DiningSession, session_id)
                    if dining_session:
                        waiter_id, waiter_name = get_waiter_assignment_from_dining_session(
                            dining_session
                        )

                # Intentar por asignación de mesa si no hay mesero aún
                if not waiter_id:
                    assignment = (
                        session.execute(
                            select(WaiterTableAssignment)
                            .options(joinedload(WaiterTableAssignment.waiter))
                            .where(
                                WaiterTableAssignment.table_id == table_id,
                                WaiterTableAssignment.is_active == True,  # noqa: E712
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if assignment and assignment.waiter:
                        waiter_id = assignment.waiter_id
                        waiter_name = assignment.waiter.name

                emit_waiter_call(
                    call_id=recent_call.id,
                    session_id=session_id,
                    table_number=table_number,
                    status="pending",
                    call_type="waiter_call",
                    order_numbers=[],
                    waiter_id=waiter_id,
                    waiter_name=waiter_name,
                    created_at=recent_call.created_at,
                )
            except Exception as emit_error:
                current_app.logger.warning(f"Error re-emitting waiter call: {emit_error}")

            return jsonify(
                {"message": "Llamada reenviada", "call_id": recent_call.id}
            ), HTTPStatus.OK

        waiter_call = WaiterCall(
            session_id=session_id if session_id else None,
            table_number=table_number,
            status="pending",
        )
        session.add(waiter_call)
        session.flush()

        # Capture values immediately after flush to avoid detached instance errors
        call_id = waiter_call.id
        waiter_call_created_at = waiter_call.created_at

        # Resolver mesero asignado (sesión o asignación de mesa)
        waiter_id, waiter_name = get_waiter_assignment_from_db(session, session_id)
        if not waiter_id:
            assignment = (
                session.execute(
                    select(WaiterTableAssignment)
                    .options(joinedload(WaiterTableAssignment.waiter))
                    .where(
                        WaiterTableAssignment.table_id == table_id,
                        WaiterTableAssignment.is_active == True,  # noqa: E712
                    )
                )
                .scalars()
                .first()
            )
            if assignment and assignment.waiter:
                waiter_id = assignment.waiter_id
                waiter_name = assignment.waiter.name

        recipient_type = "employee" if waiter_id else "all_waiters"
        notification = Notification(
            notification_type="waiter_call",
            recipient_type=recipient_type,
            recipient_id=waiter_id,
            title="Cliente solicitando atención",
            message=f"Mesa {table_number} requiere asistencia",
            data=f'{{"table_number": "{table_number}", "session_id": {session_id}, "waiter_call_id": {call_id}}}',
            priority="high",
        )
        session.add(notification)

        # Si no hay mesero asignado, alertar a administradores tras N minutos sin asignación
        if not waiter_id:
            try:
                from pronto_shared.services.business_config_service import get_config_value

                minutes_cfg = get_config_value("unassigned_table_alert_minutes", "5")
                alert_minutes = int(minutes_cfg) if str(minutes_cfg).isdigit() else 5
            except Exception:
                alert_minutes = 5

            last_assignment = (
                session.execute(
                    select(WaiterTableAssignment)
                    .where(WaiterTableAssignment.table_id == table_id)
                    .order_by(
                        WaiterTableAssignment.unassigned_at.desc().nulls_last(),
                        WaiterTableAssignment.assigned_at.desc(),
                    )
                )
                .scalars()
                .first()
            )
            base_time = (
                last_assignment.unassigned_at or last_assignment.assigned_at
                if last_assignment
                else table_created_at
            )
            if base_time and (datetime.utcnow() - base_time) > timedelta(minutes=alert_minutes):
                admin_notification = Notification(
                    notification_type="table_unassigned",
                    recipient_type="admin",
                    recipient_id=None,
                    title="Mesa sin asignar",
                    message=f"La mesa {table_number} lleva más de {alert_minutes} minutos sin mesero asignado",
                    data=f'{{"table_number": "{table_number}", "waiter_call_id": {call_id}}}',
                    priority="high",
                )
                session.add(admin_notification)

        session.commit()

        # Get order numbers if session exists (call_id and waiter_call_created_at already captured)
        if session_id:
            order_numbers = (
                session.execute(select(Order.id).where(Order.session_id == session_id))
                .scalars()
                .all()
            )
            waiter_id, waiter_name = get_waiter_assignment_from_db(session, session_id)

    current_app.logger.info(
        f"Waiter called from table {table_number}, session_id={session_id}, call_id={call_id}"
    )

    emit_waiter_call(
        call_id=call_id,
        session_id=session_id if session_id else 0,
        table_number=table_number,
        status="pending",
        order_numbers=order_numbers,
        waiter_id=waiter_id,
        waiter_name=waiter_name,
        created_at=waiter_call_created_at,
    )

    return jsonify({"success": True, "call_id": call_id, "message": "Mesero notificado"}), 200


@waiter_calls_bp.get("/call-waiter/status/<int:call_id>")
def get_waiter_call_status(call_id):
    """Check the status of a waiter call."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import WaiterCall

    with get_session() as session:
        waiter_call = (
            session.execute(select(WaiterCall).where(WaiterCall.id == call_id))
            .scalars()
            .one_or_none()
        )

        if not waiter_call:
            return jsonify({"error": "Llamada no encontrada"}), 404

        return jsonify(
            {
                "id": waiter_call.id,
                "status": waiter_call.status,
                "created_at": waiter_call.created_at.isoformat()
                if waiter_call.created_at
                else None,
                "confirmed_at": waiter_call.confirmed_at.isoformat()
                if waiter_call.confirmed_at
                else None,
                "confirmed_by": waiter_call.confirmed_by,
            }
        ), 200


@waiter_calls_bp.get("/waiter-calls/<int:call_id>/status")
def get_waiter_call_status_alt(call_id):
    """Check the status of a waiter call (alternative endpoint for frontend compatibility)."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import WaiterCall

    with get_session() as session:
        waiter_call = (
            session.execute(select(WaiterCall).where(WaiterCall.id == call_id))
            .scalars()
            .one_or_none()
        )

        if not waiter_call:
            return jsonify({"error": "Llamada no encontrada"}), 404

        return jsonify(
            {
                "id": waiter_call.id,
                "status": waiter_call.status,
                "created_at": waiter_call.created_at.isoformat()
                if waiter_call.created_at
                else None,
                "confirmed_at": waiter_call.confirmed_at.isoformat()
                if waiter_call.confirmed_at
                else None,
                "confirmed_by": waiter_call.confirmed_by,
            }
        ), 200
