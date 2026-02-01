"""
Waiter Calls API - Endpoints para llamadas de meseros
Handles pending waiter calls from customers
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from employees_app.decorators import login_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.constants import OrderStatus
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import WaiterCall
from shared.serializers import error_response, success_response
from shared.services.waiter_call_service import (
    get_waiter_assignment_from_db,
    get_waiter_assignment_from_session,
)
from shared.supabase.realtime import emit_supervisor_call, emit_waiter_call

# Create blueprint without url_prefix (inherited from parent)
waiter_calls_bp = Blueprint("waiter_calls", __name__)
logger = get_logger(__name__)


@waiter_calls_bp.get("/waiter-calls/pending")
@jwt_required
def get_pending_waiter_calls():
    """
    Obtener llamadas pendientes

    Retorna todas las llamadas de meseros que están en estado "pending".
    """
    with get_session() as db_session:
        calls = (
            db_session.execute(
                select(WaiterCall)
                .where(WaiterCall.status == "pending")
                .order_by(WaiterCall.created_at.desc())
            )
            .scalars()
            .all()
        )

        result = []
        for call in calls:
            order_numbers = []
            if call.session and call.session.orders:
                order_numbers = [
                    order.id
                    for order in call.session.orders
                    if order.workflow_status != OrderStatus.CANCELLED.value
                ]
            waiter_id, waiter_name = _resolve_waiter_assignment(db_session, call)
            result.append(
                {
                    "id": call.id,
                    "table_number": call.table_number,
                    "session_id": call.session_id,
                    "status": call.status,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "notes": call.notes,
                    "order_numbers": order_numbers,
                    "waiter_id": waiter_id,
                    "waiter_name": waiter_name,
                }
            )

        response = jsonify({"waiter_calls": result})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


@waiter_calls_bp.post("/waiter-calls/<int:call_id>/confirm")
@jwt_required
def confirm_waiter_call(call_id: int):
    """
    Confirmar llamada de mesero

    El mesero confirma que recibió la llamada y está atendiendo al cliente.
    """
    employee_id = get_employee_id()
    if not employee_id:
        return jsonify(error_response("No autorizado")), HTTPStatus.UNAUTHORIZED

    with get_session() as db_session:
        waiter_call = (
            db_session.execute(select(WaiterCall).where(WaiterCall.id == call_id))
            .scalars()
            .one_or_none()
        )

        if not waiter_call:
            return jsonify(error_response("Llamada no encontrada")), HTTPStatus.NOT_FOUND

        if waiter_call.status != "pending":
            return jsonify(
                error_response("La llamada ya fue confirmada o cancelada")
            ), HTTPStatus.BAD_REQUEST

        order_numbers = []
        if waiter_call.session and waiter_call.session.orders:
            order_numbers = [
                order.id
                for order in waiter_call.session.orders
                if order.workflow_status != OrderStatus.CANCELLED.value
            ]

        waiter_id, waiter_name = _resolve_waiter_assignment(db_session, waiter_call)

        waiter_call.status = "confirmed"
        waiter_call.confirmed_at = datetime.utcnow()
        waiter_call.confirmed_by = employee_id

        db_session.commit()

        try:
            emit_waiter_call(
                call_id=waiter_call.id,
                session_id=waiter_call.session_id or 0,
                table_number=waiter_call.table_number or "N/A",
                status="confirmed",
                call_type=waiter_call.notes,
                order_numbers=order_numbers,
                waiter_id=waiter_id,
                waiter_name=waiter_name,
                created_at=waiter_call.created_at,
            )
        except Exception as exc:
            logger.error(f"Error emitting waiter confirmation: {exc}")

        logger.info(f"Waiter call {call_id} confirmed by employee {employee_id}")

        return jsonify(
            success_response(
                {
                    "id": waiter_call.id,
                    "status": waiter_call.status,
                    "confirmed_at": waiter_call.confirmed_at.isoformat(),
                }
            )
        )


@waiter_calls_bp.post("/waiter-calls/supervisor/call")
@jwt_required
def call_supervisor():
    """
    Llamar al supervisor

    Un mesero solicita la asistencia de un supervisor.
    El supervisor recibirá una notificación con el nombre del mesero y la mesa/pedido.

    Body (opcional):
        {
            "table_number": str,
            "order_id": int
        }
    """
    employee_id = get_employee_id()
    user = get_current_user()
    employee_name = user.get("employee_name") if user else None

    if not employee_id or not employee_name:
        return jsonify(error_response("No autorizado")), HTTPStatus.UNAUTHORIZED

    # Get optional table/order info from request
    data = request.get_json(silent=True) or {}
    table_number = data.get("table_number")
    order_id = data.get("order_id")

    try:
        # Emit supervisor call notification
        emit_supervisor_call(
            employee_id=employee_id,
            employee_name=employee_name,
            table_number=table_number,
            order_id=order_id,
        )
        logger.info(
            f"Supervisor call from employee {employee_id} ({employee_name}), table={table_number}, order={order_id}"
        )
    except Exception as exc:
        # No bloqueamos al usuario si el canal en tiempo real falla
        logger.error(f"Error calling supervisor (continuing without socket): {exc}")

    return jsonify(
        success_response(
            {
                "message": "Supervisor notificado",
                "waiter_name": employee_name,
                "table_number": table_number,
            }
        )
    )


def _resolve_waiter_assignment(db_session, waiter_call: WaiterCall):
    waiter_id, waiter_name = get_waiter_assignment_from_session(waiter_call.session)
    if waiter_id:
        return waiter_id, waiter_name
    return get_waiter_assignment_from_db(db_session, waiter_call.session_id)
