"""
Debug endpoints for clients API - Only enabled in DEBUG_MODE.
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from pronto_shared.constants import OrderStatus

debug_bp = Blueprint("client_debug", __name__)


@debug_bp.get("/debug/tables")
def debug_list_tables():
    """Return available tables for the client debug panel."""
    if not current_app.config.get("DEBUG_MODE", False):
        return jsonify({"error": "Debug mode not enabled"}), HTTPStatus.FORBIDDEN

    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import Area, Table

    try:
        with get_session() as db_session:
            tables = db_session.execute(select(Table)).scalars().all()
            payload = {
                "tables": [
                    {
                        "id": t.id,
                        "table_number": t.table_number,
                        "area_id": t.area_id,
                        "code": t.code,
                    }
                    for t in tables
                ]
            }

        return jsonify(payload), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing tables (client debug): {e}")
        return jsonify({"error": "Error interno del servidor"}), HTTPStatus.INTERNAL_SERVER_ERROR


@debug_bp.post("/debug/orders/<int:order_id>/advance")
def debug_advance_order_state(order_id: int):
    """Debug endpoint to advance an order to its next state in the workflow."""
    if not current_app.config.get("DEBUG_MODE", False):
        return jsonify({"error": "Debug mode not enabled"}), HTTPStatus.FORBIDDEN

    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import Employee, Order

    try:
        with get_session() as db_session:
            order = (
                db_session.execute(select(Order).where(Order.id == order_id))
                .scalars()
                .one_or_none()
            )

            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            waiter = (
                db_session.execute(select(Employee).where(Employee.role == "waiter").limit(1))
                .scalars()
                .first()
            )

            chef = (
                db_session.execute(select(Employee).where(Employee.role == "chef").limit(1))
                .scalars()
                .first()
            )

            current_status = order.workflow_status
            next_status = None

            if current_status == "new":
                if waiter:
                    order.waiter_id = waiter.id
                    order.accepted_at = datetime.utcnow()
                order.mark_status("queued")
                next_status = "queued"

            elif current_status == "queued":
                if chef:
                    order.chef_id = chef.id
                order.mark_status("preparing")
                next_status = "preparing"

            elif current_status == "preparing":
                order.mark_status("ready")
                next_status = "ready"

            elif current_status == "ready":
                if waiter:
                    order.delivery_waiter_id = waiter.id
                order.mark_status("delivered")
                next_status = "delivered"

            elif current_status == "delivered":
                return jsonify(
                    {
                        "message": "Orden ya entregada, use checkout para continuar",
                        "order_id": order.id,
                        "status": current_status,
                    }
                ), HTTPStatus.OK

            else:
                return jsonify(
                    {"error": f"Estado desconocido: {current_status}"}
                ), HTTPStatus.BAD_REQUEST

            db_session.commit()

            return jsonify(
                {
                    "message": f"Orden avanzada de {current_status} a {next_status}",
                    "order_id": order.id,
                    "previous_status": current_status,
                    "current_status": next_status,
                }
            ), HTTPStatus.OK

    except Exception as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@debug_bp.post("/debug/sessions/<int:session_id>/request-checkout")
def debug_request_checkout(session_id: int):
    """Debug endpoint to request checkout for a session."""
    if not current_app.config.get("DEBUG_MODE", False):
        return jsonify({"error": "Debug mode not enabled"}), HTTPStatus.FORBIDDEN

    from decimal import Decimal

    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            if dining_session.status == "paid":
                return jsonify({"error": "Sesión ya cerrada"}), HTTPStatus.BAD_REQUEST

            pending_orders = (
                db_session.execute(
                    select(Order)
                    .where(Order.session_id == session_id)
                    .where(Order.workflow_status != OrderStatus.DELIVERED.value)
                )
                .scalars()
                .all()
            )

            if pending_orders:
                return jsonify(
                    {
                        "error": "Aún hay órdenes pendientes de entregar",
                        "pending_orders": [o.id for o in pending_orders],
                    }
                ), HTTPStatus.BAD_REQUEST

            all_orders = (
                db_session.execute(select(Order).where(Order.session_id == session_id))
                .scalars()
                .all()
            )

            subtotal = Decimal("0")
            tax_amount = Decimal("0")

            for order in all_orders:
                subtotal += Decimal(str(order.subtotal))
                tax_amount += Decimal(str(order.tax_amount))

            dining_session.subtotal = subtotal
            dining_session.tax_amount = tax_amount
            dining_session.total_amount = subtotal + tax_amount
            dining_session.status = "checkout_requested"

            db_session.commit()

            return jsonify(
                {
                    "message": "Checkout preparado exitosamente",
                    "session_id": session_id,
                    "subtotal": float(subtotal),
                    "tax_amount": float(tax_amount),
                    "total_amount": float(dining_session.total_amount),
                    "status": dining_session.status,
                    "mode": "DEBUG",
                }
            ), HTTPStatus.OK

    except Exception as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@debug_bp.post("/debug/sessions/<int:session_id>/simulate-payment")
def debug_simulate_payment(session_id: int):
    """Debug endpoint to simulate a payment without actual payment processing."""
    if not current_app.config.get("DEBUG_MODE", False):
        return jsonify({"error": "Debug mode not enabled"}), HTTPStatus.FORBIDDEN

    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession

    payload = request.get_json(silent=True) or {}
    payment_method = payload.get("payment_method", "cash")

    valid_methods = ["cash", "stripe", "clip"]
    if payment_method not in valid_methods:
        return jsonify(
            {"error": f"Método de pago no válido. Use: {', '.join(valid_methods)}"}
        ), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            if dining_session.status == "paid":
                return jsonify({"error": "Sesión ya pagada"}), HTTPStatus.BAD_REQUEST

            timestamp = int(datetime.utcnow().timestamp())
            if payment_method == "cash":
                payment_reference = f"debug-cash-{session_id}-{timestamp}"
            elif payment_method == "stripe":
                payment_reference = f"debug-stripe-pi_{session_id}_{timestamp}"
            elif payment_method == "clip":
                payment_reference = f"debug-clip-tx_{session_id}_{timestamp}"

            dining_session.payment_method = payment_method
            dining_session.payment_reference = payment_reference
            dining_session.total_paid = dining_session.total_amount
            dining_session.status = "closed"
            dining_session.closed_at = datetime.utcnow()

            for order in dining_session.orders:
                order.payment_status = "paid"
                order.payment_method = payment_method
                order.payment_reference = payment_reference
                order.paid_at = datetime.utcnow()
                db_session.add(order)

            db_session.add(dining_session)
            db_session.commit()

            return jsonify(
                {
                    "message": f"Pago simulado exitosamente con {payment_method}",
                    "session_id": dining_session.id,
                    "payment_method": payment_method,
                    "payment_reference": payment_reference,
                    "subtotal": float(dining_session.subtotal),
                    "tax_amount": float(dining_session.tax_amount),
                    "tip_amount": float(dining_session.tip_amount),
                    "total_amount": float(dining_session.total_amount),
                    "total_paid": float(dining_session.total_paid),
                    "status": dining_session.status,
                    "mode": "DEBUG - SIMULATED PAYMENT",
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error in debug simulate payment: {e}")
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
