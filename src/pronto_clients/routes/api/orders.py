# Fix: Add query parameter support for GET method

# Original endpoint (GET only)
@orders_bp.get("/orders/send-confirmation")
def send_order_confirmation_original():
    """Original GET-only endpoint."""
    payload = request.get_json(silent=True) or {}
    order_id = payload.get("session_id")
    if not order_id:
        return jsonify(error_response("session_id is required")), 400
    
    data, status, _ = _forward_to_api(
        "POST",
        f"/api/customer/orders/session/{order_id}/send-ticket-email",
        {}
    )
    return jsonify(data), status

# Updated endpoint (GET and POST support)
@orders_bp.get("/orders/send-confirmation")
@orders_bp.post("/orders/send-confirmation")
def send_order_confirmation():
    """
    Order confirmation endpoint.
    Supports both GET (for query) and POST (for payment confirmation).
    Forwards to pronto-api to trigger email for completed order.
    """
    from flask import Blueprint, jsonify, session, request
    
    from pronto_clients.routes.api.auth import customer_session_required
    from pronto_shared.services.customer_session_store import (
        customer_session_store,
        RedisUnavailableError,
    )
    from pronto_shared.services.email_scheduler import EmailSchedulerService
    from pronto_shared.jwt_middleware import get_current_user
    from pronto_shared.constants import OrderStatus
    from pronto_shared.db import get_session
    from pronto_shared.models import Order
    from pronto_shared.trazabilidad import get_logger
    from http import HTTPStatus
    
    logger = get_logger(__name__)
    
    def _check_session_ownership(dining_session, authed_user: dict | None) -> bool:
        """Check if authenticated user owns the dining session."""
        if not authed_user:
            return False
        session_customer_id = str(dining_session.customer_id)
        authed_customer_id = authed_user.get("customer_id") if authed_user else None
        return session_customer_id == authed_customer_id
    
    try:
        with get_session() as db_session:
            # Get order
            order = db_session.query(Order).options(
                and_(Order.session),
                joinedload(Order.session),
                joinedload(Order.items)
            ).filter(Order.id == order_id).first()
            
            if not order:
                return jsonify({"error": "Orden no encontrada"}), HTTPStatus.NOT_FOUND
            
            # Support both GET and POST methods
            if request.method == "GET":
                # Query method - return order status
                return jsonify({
                    "data": order.to_dict(),
                    "status": order.workflow_status,
                }), HTTPStatus.OK
            else:
                # POST method - send confirmation email
                order_data = request.get_json(silent=True) or {}
                payment = order_data.get("payment_method") or ""
                
                # Determine actor type
                current_user = get_current_user()
                if not current_user:
                    return jsonify({"error": "No autorizado"}), HTTPStatus.FORBIDDEN
                
                # Check if it's customer paying
                is_customer_payment = current_user.get("active_scope", "") == "customer"
                
                if is_customer_payment:
                    # Customer payment logic
                    if order.session.status == "paid":
                        return jsonify({"error": "La sesión ya está pagada"}), HTTPStatus.BAD_REQUEST
                    
                    if not payment:
                        return jsonify({"error": "Monto es requerido"}), HTTPStatus.BAD_REQUEST
                    
                    # Process payment
                    amount = float(payment.get("amount") or 0)
                    reference = (payment.get("payment_reference") or "").strip()
                    
                    # Use employee_prepare_checkout for customers
                    data, status = employee_prepare_checkout(
                        session=order,
                        customer_id=current_user.get("user_id"),
                    )
                    
                    if status != HTTPStatus.OK:
                        return jsonify(data), status
                    
                    # Create payment record
                    from pronto_shared.models import Payment
                    from datetime import datetime, timezone
                    
                    payment = Payment(
                        session=order,
                        amount=float(amount),
                        payment_method=payment,
                        payment_reference=reference,
                        created_by=current_user.get("user_id"),
                        created_at=datetime.now(timezone.utc),
                    )
                    
                    db_session.add(payment)
                    db_session.flush()
                    
                    # Mark session as paid
                    order.session.status = "paid"
                    order.session.closed_at = datetime.now(timezone.utc)
                    
                    # Send confirmation email
                    try:
                        from pronto_shared.services.waiter_call_service import emit_waiter_call
                        items_str = ", ".join([f"{i.name}" for i in order.session.items])
                        
                        emit_waiter_call(
                            "order_ready",
                            f"Orden #{order.id} lista para servir ({items_str})"
                        )
                    except Exception as e:
                        logger.warning(f"Error notificando: {e}")
                    
                    db_session.commit()
                    
                    # Return success
                    return jsonify({
                        "status": "paid",
                        "payment_id": payment.id,
                        "amount": payment.amount,
                        "payment_method": payment.method,
                        "payment_reference": f"EFECTIVO-{payment.payment_reference}",
                        "message": "Pago procesado"
                    }), HTTPStatus.CREATED
                else:
                    # Employee payment logic
                    if order.session.status == "paid":
                        return jsonify({"error": "La sesión ya está pagada"}), HTTPStatus.BAD_REQUEST
                    
                    if not payment:
                        return jsonify({"error": "Monto inválido"}), HTTPStatus.BAD_REQUEST
                    
                    # Get waiter assignment
                    try:
                        from pronto_shared.services.waiter_call_service import get_waiter_assignment_from_db
                        waiter_id = get_waiter_assignment_from_db(
                            order.session,
                            employee_id=current_user.get("user_id")
                        )
                    except Exception as e:
                        waiter_id = None
                    
                    # Use finalize_payment for employees
                    from pronto_shared.services.order_service import finalize_payment
                    from pronto_shared.constants import OrderStatus
                    
                    data, status = finalize_payment(
                        session=order,
                        employee_id=current_user.get("user_id"),
                        payment_method=payment,
                        reference=reference,
                        amount=float(amount),
                        order_status=OrderStatus.PAID.value if order.workflow_status == OrderStatus.DELIVERED.value else order.workflow_status,
                    )
                    
                    if status != HTTPStatus.OK:
                        return jsonify(data), status
                    
                    # Create payment record
                    from pronto_shared.models import Payment
                    from datetime import datetime, timezone
                    
                    payment = Payment(
                        session=order,
                        amount=float(amount),
                        payment_method=payment,
                        payment_reference=reference,
                        created_by=current_user.get("user_id"),
                        created_at=datetime.now(timezone.utc),
                    )
                    
                    db_session.add(payment)
                    db_session.flush()
                    
                    # Mark session as paid
                    order.session.status = "paid"
                    order.session.closed_at = datetime.now(timezone.utc)
                    
                    # Notify waiter
                    try:
                        emit_waiter_call(
                            "order_ready",
                            f"Orden #{order.id} lista para servir"
                        )
                    except Exception as e:
                        logger.warning(f"Error notificando: {e}")
                    
                    db_session.commit()
                    
                    # Return success
                    return jsonify({
                        "status": "paid",
                        "payment_id": payment.id,
                        "amount": payment.amount,
                        "payment_method": payment.method,
                        "payment_reference": f"EFFECTIVO-{payment.payment_reference}"
                    }), HTTPStatus.CREATED
    
    except Exception as e:
        from pronto_shared.trazabilidad import get_logger
        logger.error(f"Error procesando pago: {e}", exc_info=True)
        return jsonify(
            {"error": "Error al procesar pago"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
