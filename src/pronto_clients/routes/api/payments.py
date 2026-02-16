from pronto_clients.routes.api.auth import customer_session_required
from pronto_shared.services.customer_session_store import (
    customer_session_store,
    RedisUnavailableError,
)
from pronto_shared.services.order_service import (
    prepare_checkout as employee_prepare_checkout,
)
from pronto_shared.services.waiter_call_service import get_waiter_assignment_from_db
from pronto_shared.supabase.realtime import emit_waiter_call
from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

payments_bp = Blueprint("client_payments", __name__)


def _get_authenticated_customer() -> dict | None:
    """Get authenticated customer from flask.session + Redis."""
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return None
    try:
        if customer_session_store.is_revoked(customer_ref):
            session.pop("customer_ref", None)
            return None
        return customer_session_store.get_customer(customer_ref)
    except RedisUnavailableError:
        return None


@payments_bp.post("/sessions/<uuid:session_id>/request-payment")
@customer_session_required
def request_payment(session_id):
    """
    Customer requests payment for their session.
    Creates a WaiterCall with type 'payment_request' and notifies waiters.
    """
    from sqlalchemy import and_, select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Notification, Order, WaiterCall

    payload = request.get_json(silent=True) or {}
    payment_method = payload.get("payment_method", "").strip().lower()
    table_number = payload.get("table_number", "").strip()

    if payment_method not in ["cash", "terminal"]:
        return jsonify(
            {"error": "Método de pago inválido. Use 'cash' o 'terminal'"}
        ), HTTPStatus.BAD_REQUEST

    order_numbers = []
    waiter_call_created_at = None
    waiter_id = waiter_name = None

    with get_session() as db_session:
        dining_session = db_session.get(DiningSession, session_id)

        if not dining_session:
            return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

        # Authorization check
        authed_user = _get_authenticated_customer()
        if dining_session.customer_id != authed_user.get("id"):
            return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

        if dining_session.status in ["closed", "paid"]:
            return jsonify(
                {"error": "Esta sesión ya está cerrada"}
            ), HTTPStatus.BAD_REQUEST

        if not table_number:
            table_number = dining_session.table_number or "N/A"

        two_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=2)
        recent_payment_call = (
            db_session.execute(
                select(WaiterCall).where(
                    and_(
                        WaiterCall.session_id == session_id,
                        WaiterCall.status == "pending",
                        WaiterCall.notes.like("%payment_request%"),
                        WaiterCall.created_at >= two_minutes_ago,
                    )
                )
            )
            .scalars()
            .first()
        )

        if recent_payment_call:
            return jsonify(
                {
                    "error": "Ya existe una solicitud de pago pendiente",
                    "call_id": recent_payment_call.id,
                }
            ), HTTPStatus.CONFLICT

        waiter_call = WaiterCall(
            session_id=session_id,
            table_number=table_number,
            status="pending",
            notes=f"payment_request:{payment_method}",
        )
        db_session.add(waiter_call)
        db_session.flush()

        payment_method_label = (
            "Efectivo" if payment_method == "cash" else "Terminal (Clip)"
        )
        notification = Notification(
            notification_type="payment_request",
            recipient_type="all_waiters",
            recipient_id=None,
            title=f"Solicitud de pago - Mesa {table_number}",
            message=f"Cliente solicita pagar con {payment_method_label}",
            data=f'{{"table_number": "{table_number}", "session_id": {session_id}, "waiter_call_id": {waiter_call.id}, "payment_method": "{payment_method}"}}',
            priority="high",
        )
        db_session.add(notification)
        db_session.commit()

        call_id = waiter_call.id
        waiter_call_created_at = waiter_call.created_at

        order_numbers = (
            db_session.execute(select(Order.id).where(Order.session_id == session_id))
            .scalars()
            .all()
        )
        waiter_id, waiter_name = get_waiter_assignment_from_db(db_session, session_id)

    logger.info(
        f"Payment requested for session {session_id}",
        table=table_number,
        method=payment_method,
        call_id=call_id
    )

    emit_waiter_call(
        call_id=call_id,
        session_id=session_id,
        table_number=table_number,
        status="pending",
        call_type=f"payment_request:{payment_method}",
        order_numbers=order_numbers,
        waiter_id=waiter_id,
        waiter_name=waiter_name,
        created_at=waiter_call_created_at,
    )

    return jsonify(
        {
            "success": True,
            "call_id": call_id,
            "message": "Solicitud de pago enviada",
            "payment_method": payment_method,
        }
    ), HTTPStatus.OK


@payments_bp.post("/confirm-tip")
@customer_session_required
def confirm_tip():
    """Save the tip amount for a dining session."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    tip_amount = payload.get("tip_amount", 0)

    if not session_id:
        return jsonify({"error": "Session ID is required"}), HTTPStatus.BAD_REQUEST

    try:
        tip_amount = Decimal(str(tip_amount))
        if tip_amount < 0:
            return jsonify(
                {"error": "Tip amount must be non-negative"}
            ), HTTPStatus.BAD_REQUEST
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid tip amount"}), HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        dining_session = (
            db_session.execute(
                select(DiningSession).where(DiningSession.id == session_id)
            )
            .scalars()
            .one_or_none()
        )

        if not dining_session:
            return jsonify({"error": "Session not found"}), HTTPStatus.NOT_FOUND

        # Authorization check
        authed_user = _get_authenticated_customer()
        if dining_session.customer_id != authed_user.get("id"):
            return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

        if dining_session.status != "open":
            return jsonify({"error": "Session is not open"}), HTTPStatus.BAD_REQUEST

        dining_session.tip_amount = tip_amount
        if tip_amount > 0:
            dining_session.tip_requested_at = datetime.now(timezone.utc)
            dining_session.tip_confirmed_at = datetime.now(timezone.utc)

        dining_session.recompute_totals()

        orders = dining_session.orders
        if orders and tip_amount > 0:
            session_subtotal = dining_session.subtotal
            if session_subtotal > 0:
                for order in orders:
                    order_proportion = Decimal(order.subtotal) / Decimal(
                        session_subtotal
                    )
                    order.tip_amount = tip_amount * order_proportion
                    order.total_amount = (
                        order.subtotal + order.tax_amount + order.tip_amount
                    )

        db_session.commit()

        logger.info(
            f"Tip confirmed: session_id={session_id}",
            tip_amount=float(tip_amount),
            new_total=float(dining_session.total_amount)
        )

        return jsonify(
            {
                "status": "ok",
                "message": "Propina guardada exitosamente",
                "tip_amount": float(tip_amount),
                "new_total": float(dining_session.total_amount),
                "session_id": session_id,
            }
        ), HTTPStatus.OK


@payments_bp.post("/sessions/<uuid:session_id>/checkout")
@customer_session_required
def request_session_checkout(session_id):
    """Request checkout for a dining session."""
    from sqlalchemy import select

    from pronto_shared.constants import OrderStatus
    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Authorization check
            authed_user = _get_authenticated_customer()
            if dining_session.customer_id != authed_user.get("id"):
                return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

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

        checkout_payload, checkout_status = employee_prepare_checkout(session_id)
        if checkout_status != HTTPStatus.OK:
            return jsonify(checkout_payload), checkout_status

        totals = checkout_payload.get("totals", {})
        customer_data = checkout_payload.get("customer") or {}
        customer_email = (customer_data.get("email") or "").lower()
        can_pay_digital = bool(
            customer_email and not customer_email.startswith("anonimo+")
        )

        response_data = {
            "status": "ok",
            "message": "Sesión lista para pago",
            "session_id": checkout_payload.get("id"),
            "subtotal": totals.get("subtotal"),
            "tax_amount": totals.get("tax_amount"),
            "tip_amount": totals.get("tip_amount"),
            "total_amount": totals.get("total_amount"),
            "session_status": checkout_payload.get("status"),
            "customer": customer_data,
            "can_pay_digitally": can_pay_digital,
        }

        if checkout_payload.get("waiter_call_id"):
            response_data["waiter_call_id"] = checkout_payload["waiter_call_id"]

        return jsonify(response_data), HTTPStatus.OK

    except Exception as e:
        logger.error("Error requesting checkout", error={"exception": str(e), "traceback": True})
        return jsonify(
            {"error": "Error al solicitar cuenta"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@payments_bp.post("/session/<uuid:session_id>/request-check")
@customer_session_required
def request_check(session_id):
    """Request check/bill for a dining session."""
    from sqlalchemy import select

    from pronto_shared.constants import OrderStatus
    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Authorization check
            authed_user = _get_authenticated_customer()
            if dining_session.customer_id != authed_user.get("id"):
                return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

            if dining_session.status == "paid":
                return jsonify({"error": "Sesión ya cerrada"}), HTTPStatus.BAD_REQUEST

            delivered_orders = (
                db_session.execute(
                    select(Order)
                    .where(Order.session_id == session_id)
                    .where(Order.workflow_status == OrderStatus.DELIVERED.value)
                )
                .scalars()
                .all()
            )

            if not delivered_orders:
                return jsonify(
                    {"error": "Espera a que se entregue tu pedido para pedir la cuenta"}
                ), HTTPStatus.BAD_REQUEST

            dining_session.check_requested_at = datetime.now(timezone.utc)
            db_session.commit()

            return jsonify(
                {
                    "status": "ok",
                    "message": "Cuenta solicitada correctamente",
                    "session_id": session_id,
                    "check_requested_at": dining_session.check_requested_at.isoformat(),
                }
            ), HTTPStatus.OK

    except Exception as e:
        logger.error("Error requesting check", error={"exception": str(e), "traceback": True})
        return jsonify(
            {"error": "Error al solicitar cuenta"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@payments_bp.get("/session/<uuid:session_id>/validate")
@customer_session_required
def validate_session(session_id):
    """Validate if a session exists and return its basic info for client-side validation."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Authorization check
            authed_user = _get_authenticated_customer()
            if dining_session.customer_id != authed_user.get("id"):
                return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

            # Get anonymous client ID if customer exists
            anonymous_client_id = None
            if dining_session.customer and dining_session.customer.email:
                email = dining_session.customer.email
                if email.startswith("anonimo+"):
                    # Extract the anonymous client ID from email format: anonimo+{client_id}@...
                    anonymous_client_id = email.split("@")[0].replace("anonimo+", "")

            return jsonify(
                {
                    "session": {
                        "id": dining_session.id,
                        "status": dining_session.status,
                        "created_at": dining_session.opened_at.isoformat()
                        if dining_session.opened_at
                        else None,
                    },
                    "anonymous_client_id": anonymous_client_id,
                }
            )
    except Exception as e:
        logger.error("Error validating session", error={"exception": str(e)})
        return jsonify(
            {"error": "Error al validar sesión"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@payments_bp.get("/session/<uuid:session_id>/orders")
@customer_session_required
def get_session_orders(session_id):
    """Get all orders for a specific session with their items and status."""
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(
                    select(DiningSession).where(DiningSession.id == session_id)
                )
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Authorization check: Ensure the authenticated customer owns this session
            authed_user = _get_authenticated_customer()
            if not authed_user or dining_session.customer_id != authed_user.get("id"):
                return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN

            orders = (
                db_session.execute(
                    select(Order)
                    .where(Order.session_id == session_id)
                    .order_by(Order.created_at.desc())
                )
                .scalars()
                .all()
            )

            orders_data = []
            for order in orders:
                items = []
                for order_item in order.items:
                    item_total = float(order_item.unit_price) * order_item.quantity

                    modifiers_list = []
                    if order_item.modifiers:
                        for mod in order_item.modifiers:
                            modifier_price = (
                                float(mod.unit_price_adjustment) * mod.quantity
                            )
                            item_total += modifier_price
                            modifiers_list.append(
                                {
                                    "name": mod.modifier.name
                                    if mod.modifier
                                    else "Modificador",
                                    "price": float(mod.unit_price_adjustment),
                                    "quantity": mod.quantity,
                                }
                            )

                    item_data = {
                        "id": order_item.id,
                        "name": order_item.menu_item.name
                        if order_item.menu_item
                        else "Producto eliminado",
                        "quantity": order_item.quantity,
                        "unit_price": float(order_item.unit_price),
                        "total_price": item_total,
                        "modifiers": modifiers_list,
                    }
                    items.append(item_data)

                orders_data.append(
                    {
                        "id": order.id,
                        "order_id": order.id,
                        "created_at": order.created_at.isoformat()
                        if order.created_at
                        else None,
                        "workflow_status": order.workflow_status,
                        "status": order.workflow_status,
                        "payment_status": order.payment_status,
                        "subtotal": float(order.subtotal),
                        "tax_amount": float(order.tax_amount)
                        if order.tax_amount
                        else 0,
                        "tip_amount": float(order.tip_amount)
                        if order.tip_amount
                        else 0,
                        "total_amount": float(order.total_amount),
                        "total": float(order.total_amount),
                        "items": items,
                        "notes": order.session.notes if order.session else None,
                        "customer_notes": order.session.notes
                        if order.session
                        else None,
                    }
                )

            customer_email = ""
            if dining_session.customer and dining_session.customer.email:
                customer_email = dining_session.customer.email or ""
            can_pay_digitally = bool(
                customer_email and not customer_email.lower().startswith("anonimo+")
            )

            session_summary = {
                "id": dining_session.id,
                "session_id": dining_session.id,
                "table_number": dining_session.table_number,
                "status": dining_session.status,
                "subtotal": float(dining_session.subtotal),
                "tax_amount": float(dining_session.tax_amount)
                if dining_session.tax_amount
                else 0,
                "tip_amount": float(dining_session.tip_amount)
                if dining_session.tip_amount
                else 0,
                "total_amount": float(dining_session.total_amount),
                "total": float(dining_session.total_amount),
                "created_at": dining_session.opened_at.isoformat()
                if dining_session.opened_at
                else None,
                "can_pay_digitally": can_pay_digitally,
            }

            return jsonify(
                {
                    "orders": orders_data,
                    "session": session_summary,
                    "session_summary": session_summary,
                    "total_orders": len(orders_data),
                }
            ), HTTPStatus.OK

    except Exception as e:
        logger.error("Error fetching session orders", error={"exception": str(e)})
        return jsonify(
            {"error": "Error al obtener pedidos"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
