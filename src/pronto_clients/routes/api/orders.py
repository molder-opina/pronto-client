"""
Orders endpoints for clients API.
"""

from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from pronto_clients.services.order_service import OrderValidationError
from pronto_clients.services.order_service import create_order as create_order_service
from pronto_clients.utils.input_sanitizer import sanitize_email
from pronto_shared.constants import OrderStatus
from pronto_shared.db import get_session
from pronto_shared.models import Customer, DiningSession, Order, OrderItem, OrderItemModifier
from pronto_shared.security_middleware import rate_limit
from pronto_shared.services.notifications_service import send_order_confirmation_email
from pronto_shared.services.order_service import cancel_order as cancel_order_service
from pronto_shared.supabase.realtime import emit_new_order, emit_order_status_change

orders_bp = Blueprint("client_orders", __name__)


def _debug(msg: str, **extra) -> None:
    """Lightweight logger for client orders diagnostics."""
    try:
        current_app.logger.info(f"[ClientOrders] {msg} | {extra}")
    except Exception:
        # Fallback to stderr to avoid hiding logging failures
        import sys

        sys.stderr.write(f"[ClientOrders][LOGGING_FAILURE] {msg} | {extra}\n")


@orders_bp.post("/orders")
@rate_limit(max_requests=10, window_seconds=60, key_prefix="create_order_")
def create_order_endpoint():
    """
    Create an order from the payload sent by the client application.

    Validations:
    - Maximum 50 items per order
    - Valid customer data structure
    - Sanitized inputs
    """
    payload = request.get_json(silent=True) or {}
    customer_data = payload.get("customer") or {}
    items_data = payload.get("items") or []
    notes = payload.get("notes")

    _debug(
        "create_order_endpoint received",
        items_count=len(items_data),
        items_data=str(items_data)[:200],
    )

    # Validate items count
    if not items_data:
        return jsonify(
            {"error": "La orden debe contener al menos un producto"}
        ), HTTPStatus.BAD_REQUEST

    # Validate each item has a valid menu_item_id
    valid_items = []
    for i, item in enumerate(items_data):
        menu_item_id = item.get("menu_item_id")
        if menu_item_id is None or menu_item_id == "":
            _debug("skipping_invalid_item", index=i, item=item)
            continue
        valid_items.append(item)

    _debug("valid_items_filtered", original_count=len(items_data), valid_count=len(valid_items))

    if not valid_items:
        return jsonify(
            {"error": "La orden debe contener al menos un producto válido"}
        ), HTTPStatus.BAD_REQUEST

    if len(valid_items) > 50:
        return jsonify(
            {"error": "La orden no puede contener más de 50 productos"}
        ), HTTPStatus.BAD_REQUEST

    # Get existing_session_id from Flask session or payload (for backwards compatibility)
    existing_session_id = session.get("dining_session_id") or payload.get("session_id")

    try:
        response, status = create_order_service(
            customer_data,
            valid_items,  # Use validated items only
            notes,
            tax_rate=current_app.config.get("TAX_RATE", 0.16),
            existing_session_id=existing_session_id,
            table_number=payload.get("table_number"),
            anonymous_client_id=payload.get("anonymous_client_id"),
            auto_ready_quick_serve=current_app.config.get("AUTO_READY_QUICK_SERVE", False),
        )
        _debug(
            "create_order_endpoint",
            status=status,
            session_id=response.get("session_id"),
            order_id=response.get("order_id"),
        )

        # Store session_id in Flask session for future requests
        if status == HTTPStatus.CREATED and response.get("session_id"):
            session["dining_session_id"] = response["session_id"]
            session["customer_data"] = {
                "name": customer_data.get("name"),
                "email": customer_data.get("email"),
                "phone": customer_data.get("phone"),
            }
            session.modified = True

        # Send notifications on successful order creation
        if status == HTTPStatus.CREATED and response.get("order_id"):
            # Emit Redis event
            try:
                emit_new_order(
                    order_id=response["order_id"],
                    session_id=response.get("session_id"),
                    table_number=payload.get("table_number"),
                    order_data={"items_count": len(valid_items), "notes": notes},
                )
            except Exception as ws_error:
                current_app.logger.error(f"Error sending Redis notification: {ws_error}")

            # Send SSE notification to waiters via Redis stream
            try:
                from pronto_shared.notification_stream_service import notify_waiters

                order_id = response["order_id"]
                table_number = payload.get("table_number", "N/A")

                notify_waiters(
                    "new_order",
                    "Nuevo pedido",
                    f"Nuevo pedido #{order_id} - Mesa {table_number}",
                    {"order_id": order_id, "table_number": table_number},
                    priority="high",
                )
            except Exception as notification_error:
                current_app.logger.error(f"Error sending notification: {notification_error}")

        return jsonify(response), status
    except OrderValidationError as exc:
        current_app.logger.warning(f"Order validation error: {exc}")
        return jsonify({"error": str(exc)}), exc.status
    except Exception as e:
        current_app.logger.error(f"Error creating order: {e}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.post("/orders/<int:order_id>/cancel")
def cancel_order_endpoint(order_id: int):
    """Allow customers to cancel an unattended order."""
    payload = request.get_json(silent=True) or {}
    session_id = session.get("dining_session_id") or payload.get("session_id")
    reason = payload.get("reason")

    if not session_id:
        return jsonify({"error": "No hay sesión activa"}), HTTPStatus.BAD_REQUEST

    response, status = cancel_order_service(
        order_id,
        actor_scope="client",
        actor_id=session.get("customer_id"),
        session_id=session_id,
        reason=reason,
    )

    # Clear Flask session on successful cancellation
    if status == HTTPStatus.OK:
        session.pop("dining_session_id", None)
        session.pop("customer_data", None)
        session.modified = True

    if status == HTTPStatus.OK:
        emit_order_status_change(
            order_id=order_id,
            status="cancelled",
            session_id=session_id,
            table_number=response.get("session", {}).get("table_number"),
        )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/modify")
def modify_order_endpoint(order_id: int):
    """
    Allow customers to modify their orders (only before waiter accepts).
    """
    from pronto_shared.constants import ModificationInitiator
    from pronto_shared.services.order_modification_service import create_modification

    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customer_id")
    changes = payload.get("changes")

    if not customer_id:
        return jsonify({"error": "customer_id es requerido"}), HTTPStatus.BAD_REQUEST

    if not changes or not isinstance(changes, dict):
        return jsonify(
            {"error": "changes es requerido y debe ser un objeto"}
        ), HTTPStatus.BAD_REQUEST

    response, status = create_modification(
        order_id=order_id,
        changes_data=changes,
        initiated_by_role=ModificationInitiator.CUSTOMER.value,
        customer_id=customer_id,
    )

    return jsonify(response), status


@orders_bp.post("/modifications/<int:modification_id>/approve")
def approve_modification_endpoint(modification_id: int):
    """Allow customers to approve waiter-initiated modifications."""
    from pronto_shared.services.order_modification_service import approve_modification

    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customer_id")

    if not customer_id:
        return jsonify({"error": "customer_id es requerido"}), HTTPStatus.BAD_REQUEST

    response, status = approve_modification(modification_id, customer_id)
    return jsonify(response), status


@orders_bp.post("/modifications/<int:modification_id>/reject")
def reject_modification_endpoint(modification_id: int):
    """Allow customers to reject waiter-initiated modifications."""
    from pronto_shared.services.order_modification_service import reject_modification

    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customer_id")
    reason = payload.get("reason")

    if not customer_id:
        return jsonify({"error": "customer_id es requerido"}), HTTPStatus.BAD_REQUEST

    response, status = reject_modification(modification_id, customer_id, reason)
    return jsonify(response), status


@orders_bp.get("/modifications/<int:modification_id>")
def get_modification_endpoint(modification_id: int):
    """Get details of a modification request."""
    from pronto_shared.services.order_modification_service import get_modification_details

    response, status = get_modification_details(modification_id)
    return jsonify(response), status


@orders_bp.get("/session/<int:session_id>/orders")
def get_session_orders(session_id: int):
    """Return orders for a session (used by client active orders tab)."""
    from pronto_shared.serializers import serialize_order

    try:
        with get_session() as db_session:
            session_obj = db_session.get(DiningSession, session_id)
            if not session_obj:
                _debug("get_session_orders not found", session_id=session_id)
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Eager load relationships to avoid lazy-load issues during serialization
            orders = (
                db_session.execute(
                    select(Order)
                    .options(
                        joinedload(Order.items).joinedload(OrderItem.menu_item),
                        joinedload(Order.items)
                        .joinedload(OrderItem.modifiers)
                        .joinedload(OrderItemModifier.modifier),
                        joinedload(Order.session),
                        joinedload(Order.customer),
                        joinedload(Order.waiter),
                        joinedload(Order.chef),
                        joinedload(Order.delivery_waiter),
                    )
                    .where(
                        Order.session_id == session_id,
                        Order.workflow_status != OrderStatus.CANCELLED.value,
                    )
                )
                .unique()
                .scalars()
                .all()
            )

            _debug(
                "get_session_orders fetched",
                session_id=session_id,
                session_status=session_obj.status,
                orders_count=len(orders),
                total_amount=float(session_obj.total_amount or 0),
            )

            # Recompute totals defensively
            try:
                session_obj.recompute_totals()
            except Exception as recompute_err:
                current_app.logger.warning(
                    f"[Client] Could not recompute totals for session {session_id}: {recompute_err}"
                )

            serialized_orders = []
            for order in orders:
                try:
                    serialized_orders.append(
                        serialize_order(order, scope="client", session=db_session)
                    )
                except Exception as ser_err:
                    current_app.logger.error(
                        f"[Client] Error serializing order {order.id} in session {session_id}: {ser_err}",
                        exc_info=True,
                    )

            _debug(
                "get_session_orders serialized",
                session_id=session_id,
                serialized_count=len(serialized_orders),
            )

            return jsonify(
                {
                    "session": {
                        "id": session_obj.id,
                        "status": session_obj.status,
                        "table_number": session_obj.table_number,
                        "total_amount": float(session_obj.total_amount or 0),
                        "anonymous_client_id": _extract_anonymous_id(session_obj.customer),
                    },
                    "orders": serialized_orders,
                }
            ), HTTPStatus.OK
    except Exception as exc:
        current_app.logger.error(
            f"[Client] Error fetching session orders {session_id}: {exc}", exc_info=True
        )
        return jsonify({"error": "Error al cargar órdenes"}), HTTPStatus.INTERNAL_SERVER_ERROR


def _extract_anonymous_id(customer: Customer | None) -> str | None:
    if not customer or not customer.email:
        return None
    email = customer.email
    if email.startswith("anonimo+"):
        return email.split("@")[0].replace("anonimo+", "")
    return None


@orders_bp.get("/session/validate")
def validate_current_session():
    """
    Validate the current session stored in Flask session (server-side cookie).
    This is the new server-controlled approach - no session_id from client.

    Returns current session state if valid, or 404 if no active session.
    """
    session_id = session.get("dining_session_id")

    if not session_id:
        _debug("validate_current_session no session in Flask session")
        return jsonify({"error": "No hay sesión activa"}), HTTPStatus.NOT_FOUND

    try:
        with get_session() as db_session:
            session_obj = db_session.get(DiningSession, session_id)
            if not session_obj:
                _debug("validate_current_session not found in DB", session_id=session_id)
                # Clear invalid session from Flask session
                session.pop("dining_session_id", None)
                session.pop("customer_data", None)
                session.modified = True
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            # Check if session is finished
            finished_statuses = ["closed", "paid", "billed", "cancelled"]
            if session_obj.status in finished_statuses:
                _debug(
                    "validate_current_session finished",
                    session_id=session_id,
                    status=session_obj.status,
                )
                # Clear finished session from Flask session
                session.pop("dining_session_id", None)
                session.pop("customer_data", None)
                session.modified = True
                return jsonify({"error": "Sesión finalizada"}), HTTPStatus.GONE

            customer = (
                db_session.get(Customer, session_obj.customer_id)
                if session_obj.customer_id
                else None
            )
            anon_id = _extract_anonymous_id(customer)

            _debug(
                "validate_current_session ok",
                session_id=session_id,
                status=session_obj.status,
                table=session_obj.table_number,
                total=float(session_obj.total_amount or 0),
            )

            return jsonify(
                {
                    "session": {
                        "id": session_obj.id,
                        "status": session_obj.status,
                        "table_number": session_obj.table_number,
                        "total_amount": float(session_obj.total_amount or 0),
                    },
                    "anonymous_client_id": anon_id,
                }
            ), HTTPStatus.OK
    except Exception as exc:
        current_app.logger.error(f"[Client] Error validating current session: {exc}", exc_info=True)
        return jsonify({"error": "Error al validar sesión"}), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.get("/session/<int:session_id>/validate")
def validate_session(session_id: int):
    """
    DEPRECATED: Use /api/session/validate instead (no session_id parameter).
    Legacy endpoint for backwards compatibility.
    Validates session by ID from URL parameter instead of Flask session.
    """
    try:
        with get_session() as db_session:
            session_obj = db_session.get(DiningSession, session_id)
            if not session_obj:
                _debug("validate_session not found", session_id=session_id)
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            customer = (
                db_session.get(Customer, session_obj.customer_id)
                if session_obj.customer_id
                else None
            )
            anon_id = _extract_anonymous_id(customer)

            _debug(
                "validate_session ok",
                session_id=session_id,
                status=session_obj.status,
                table=session_obj.table_number,
                total=float(session_obj.total_amount or 0),
            )

            return jsonify(
                {
                    "session": {
                        "id": session_obj.id,
                        "status": session_obj.status,
                        "table_number": session_obj.table_number,
                        "total_amount": float(session_obj.total_amount or 0),
                    },
                    "anonymous_client_id": anon_id,
                }
            ), HTTPStatus.OK
    except Exception as exc:
        current_app.logger.error(
            f"[Client] Error validating session {session_id}: {exc}", exc_info=True
        )
        return jsonify({"error": "Error al validar sesión"}), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.post("/orders/<int:order_id>/request-check")
def request_order_check(order_id: int):
    """
    Request check/payment for a specific order (individual checkout).
    This allows customers to pay for orders individually in a multi-order session.
    """
    from datetime import datetime
    from decimal import Decimal

    try:
        with get_session() as db_session:
            # Load order with relationships
            order = (
                db_session.query(Order)
                .options(
                    joinedload(Order.items).joinedload(OrderItem.menu_item),
                    joinedload(Order.session),
                    joinedload(Order.customer),
                )
                .filter(Order.id == order_id)
                .first()
            )

            if not order:
                _debug("request_order_check order not found", order_id=order_id)
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            # Verify order is delivered
            if order.workflow_status != OrderStatus.DELIVERED.value:
                return jsonify(
                    {
                        "error": "La orden debe estar entregada para pedir la cuenta",
                        "current_status": order.workflow_status,
                    }
                ), HTTPStatus.BAD_REQUEST

            # Verify order is not already paid or cancelled
            if order.payment_status in ["paid", "refunded"]:
                return jsonify({"error": "La orden ya fue pagada"}), HTTPStatus.BAD_REQUEST

            if order.workflow_status == OrderStatus.CANCELLED.value:
                return jsonify({"error": "La orden está cancelada"}), HTTPStatus.BAD_REQUEST

            # Mark order as awaiting payment
            order.workflow_status = OrderStatus.AWAITING_PAYMENT.value
            order.check_requested_at = datetime.utcnow()

            # Calculate order totals
            subtotal = sum(Decimal(str(item.unit_price)) * item.quantity for item in order.items)

            # Get tax rate from config (default 16%)
            tax_rate = Decimal(str(current_app.config.get("TAX_RATE", 0.16)))
            tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
            total_amount = subtotal + tax_amount

            db_session.add(order)
            db_session.commit()

            _debug(
                "request_order_check ok",
                order_id=order_id,
                session_id=order.session_id,
                subtotal=float(subtotal),
                total=float(total_amount),
            )

            return jsonify(
                {
                    "status": "ok",
                    "message": "Cuenta solicitada para esta orden",
                    "order_id": order.id,
                    "session_id": order.session_id,
                    "subtotal": float(subtotal),
                    "tax_amount": float(tax_amount),
                    "total_amount": float(total_amount),
                    "payment_status": order.payment_status,
                    "check_requested_at": order.check_requested_at.isoformat()
                    if order.check_requested_at
                    else None,
                }
            ), HTTPStatus.OK

    except Exception as exc:
        current_app.logger.error(
            f"[Client] Error requesting check for order {order_id}: {exc}", exc_info=True
        )
        return jsonify({"error": "Error al solicitar cuenta"}), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.get("/orders/history")
def get_orders_history():
    """
    Get order history for a customer by email.
    Used by the profile "My Orders" section.

    Query params:
        - email: Customer email (required)
        - status: Filter by status (all, active, completed, cancelled)
        - limit: Max number of orders (default 20)

    Returns: List of past orders with items and totals
    """
    from pronto_shared.security import hash_identifier
    from pronto_shared.serializers import serialize_order

    email = request.args.get("email")
    status_filter = request.args.get("status", "all")
    limit = min(int(request.args.get("limit", 20)), 100)

    if not email:
        return jsonify({"error": "Email es requerido"}), HTTPStatus.BAD_REQUEST

    try:
        sanitized_email = sanitize_email(email)
    except Exception:
        return jsonify({"error": "Email inválido"}), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            email_hash = hash_identifier(sanitized_email)
            customer = (
                db_session.execute(select(Customer).where(Customer.email_hash == email_hash))
                .scalars()
                .first()
            )

            if not customer:
                _debug("get_orders_history customer not found", email=sanitized_email)
                return jsonify(
                    {"orders": [], "message": "No se encontraron órdenes"}
                ), HTTPStatus.OK

            # Build query for orders
            query = (
                db_session.query(Order)
                .options(
                    joinedload(Order.items).joinedload(OrderItem.menu_item),
                    joinedload(Order.items).joinedload(OrderItem.modifiers),
                    joinedload(Order.session),
                )
                .where(Order.customer_id == customer.id)
                .order_by(Order.created_at.desc())
                .limit(limit)
            )

            # Apply status filter
            if status_filter == "active":
                query = query.where(
                    Order.workflow_status.in_(
                        [
                            OrderStatus.NEW.value,
                            OrderStatus.QUEUED.value,
                            OrderStatus.PREPARING.value,
                            OrderStatus.READY.value,
                            OrderStatus.DELIVERED.value,
                            OrderStatus.AWAITING_PAYMENT.value,
                        ]
                    )
                )
            elif status_filter == "completed":
                query = query.where(Order.workflow_status == OrderStatus.DELIVERED.value)
            elif status_filter == "cancelled":
                query = query.where(Order.workflow_status == OrderStatus.CANCELLED.value)

            orders = query.all()

            _debug(
                "get_orders_history fetched",
                email=sanitized_email,
                customer_id=customer.id,
                orders_count=len(orders),
                status_filter=status_filter,
            )

            serialized_orders = []
            for order in orders:
                try:
                    order_data = serialize_order(order, scope="client")
                    order_data["items_summary"] = [
                        {
                            "name": item.name,
                            "quantity": item.quantity,
                            "price": float(item.unit_price * item.quantity)
                            if item.unit_price
                            else 0,
                        }
                        for item in order.items
                    ]
                    order_data["items_count"] = sum(item.quantity for item in order.items)
                    serialized_orders.append(order_data)
                except Exception as ser_err:
                    current_app.logger.error(
                        f"[Client] Error serializing order {order.id}: {ser_err}", exc_info=True
                    )

            return jsonify(
                {
                    "orders": serialized_orders,
                    "total": len(serialized_orders),
                    "customer": {"id": customer.id, "name": customer.name, "email": customer.email},
                }
            ), HTTPStatus.OK

    except Exception as exc:
        current_app.logger.error(f"[Client] Error fetching orders history: {exc}", exc_info=True)
        return jsonify(
            {"error": "Error al cargar historial de órdenes"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.get("/orders/<int:order_id>")
def get_order_details(order_id: int):
    """
    Get detailed information for a specific order.
    """
    from pronto_shared.serializers import serialize_order

    try:
        with get_session() as db_session:
            order = (
                db_session.query(Order)
                .options(
                    joinedload(Order.items).joinedload(OrderItem.menu_item),
                    joinedload(Order.items).joinedload(OrderItem.modifiers),
                    joinedload(Order.session),
                    joinedload(Order.customer),
                    joinedload(Order.waiter),
                    joinedload(Order.chef),
                )
                .filter(Order.id == order_id)
                .first()
            )

            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            order_data = serialize_order(order, scope="client")

            _debug("get_order_details", order_id=order_id, status=order.workflow_status)

            return jsonify({"order": order_data}), HTTPStatus.OK

    except Exception as exc:
        current_app.logger.error(f"[Client] Error fetching order {order_id}: {exc}", exc_info=True)
        return jsonify(
            {"error": "Error al cargar detalles de la orden"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.get("/session/<int:session_id>/timeout")
def get_session_timeout(session_id: int):
    """
    Get session expiration time for timeout monitoring.
    Returns the estimated expiration timestamp for client-side timeout warnings.
    """
    from datetime import datetime, timedelta

    finished_statuses = {"closed", "paid", "billed", "cancelled"}

    try:
        with get_session() as db_session:
            session_obj = db_session.get(DiningSession, session_id)

            if not session_obj:
                _debug("get_session_timeout session not found", session_id=session_id)
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            if session_obj.status in finished_statuses:
                _debug(
                    "get_session_timeout session finished",
                    session_id=session_id,
                    status=session_obj.status,
                )
                return jsonify(
                    {"error": "Sesión finalizada", "status": session_obj.status, "expires_at": None}
                ), HTTPStatus.OK

            session_timeout_minutes = current_app.config.get("SESSION_TIMEOUT_MINUTES", 120)
            now = datetime.utcnow()

            if session_obj.opened_at:
                expires_at = session_obj.opened_at + timedelta(minutes=session_timeout_minutes)
                time_until_expiry = (expires_at - now).total_seconds() * 1000
            else:
                expires_at = now + timedelta(minutes=session_timeout_minutes)
                time_until_expiry = session_timeout_minutes * 60 * 1000

            _debug(
                "get_session_timeout ok",
                session_id=session_id,
                status=session_obj.status,
                expires_at=expires_at.isoformat(),
                time_until_expiry_ms=time_until_expiry,
            )

            return jsonify(
                {
                    "session_id": session_id,
                    "status": session_obj.status,
                    "expires_at": expires_at.isoformat() + "Z",
                    "time_until_expiry_ms": max(0, time_until_expiry),
                    "timeout_minutes": session_timeout_minutes,
                }
            ), HTTPStatus.OK

    except Exception as exc:
        current_app.logger.error(
            f"[Client] Error fetching session timeout {session_id}: {exc}", exc_info=True
        )
        return jsonify(
            {"error": "Error al obtener tiempo de sesión"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.post("/orders/send-confirmation")
def send_confirmation_endpoint():
    """
    Send order confirmation email to customer.

    Body:
        - order_id: int (required)
        - email: str (optional, will use customer email if not provided)

    Returns:
        Success message if email sent
    """
    payload = request.get_json(silent=True) or {}
    order_id = payload.get("order_id")

    if not order_id:
        return jsonify({"error": "order_id es requerido"}), HTTPStatus.BAD_REQUEST

    try:
        sent = send_order_confirmation_email(order_id)
        if sent:
            return jsonify({"message": "Email de confirmación enviado"}), HTTPStatus.OK
        else:
            return jsonify(
                {
                    "message": "Email no enviado (servicio deshabilitado o sin email válido)",
                    "sent": False,
                }
            ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error enviando confirmación: {e}", exc_info=True)
        return jsonify({"error": "Error al enviar email"}), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.post("/orders/<int:order_id>/received")
def mark_order_received(order_id: int):
    """
    Mark an order as received by the customer.

    This is called when the customer clicks "Recibida" on a ready order.
    Changes order status to 'delivered'.

    Returns:
        Success message if order marked as received
    """
    try:
        with get_session() as db_session:
            order = db_session.get(Order, order_id)
            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND

            # Only allow marking as received if order is ready
            if order.workflow_status != OrderStatus.READY.value:
                return jsonify(
                    {"error": "La orden debe estar lista para marcarse como recibida"}
                ), HTTPStatus.BAD_REQUEST

            # Update order status to delivered
            order.mark_status(OrderStatus.DELIVERED.value)

            # Emit status change for real-time updates
            emit_order_status_change(order_id, OrderStatus.DELIVERED.value)

            db_session.commit()

            _debug("order_marked_received", order_id=order_id)

            return jsonify(
                {
                    "message": f"Orden #{order_id} marcada como recibida",
                    "order_id": order_id,
                    "status": OrderStatus.DELIVERED.value,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error marking order as received: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al marcar orden como recibida"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
