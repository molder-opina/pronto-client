"""
Sessions API - Endpoints para gestión de sesiones (cuentas)
Handles checkout, tips, payments, and ticket operations
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import select

from employees_app.decorators import role_required
from shared.audit_middleware import audit_action
from shared.constants import OrderStatus, Roles, SessionStatus
from shared.logging_config import get_logger
from shared.serializers import error_response
from shared.services.order_service import (
    apply_tip,
    close_session,
    confirm_partial_payment,
    confirm_payment,
    finalize_payment,
    generate_ticket,
    list_all_sessions,
    list_closed_sessions,
    prepare_checkout,
    resend_ticket,
    update_customer_contact,
)

logger = get_logger(__name__)

# Create blueprint without url_prefix (inherited from parent)
sessions_bp = Blueprint("sessions", __name__)


def _normalize_customer_email(email: str | None) -> str | None:
    if not email:
        return None
    cleaned = email.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in {"none", "null", "undefined"}:
        return None
    if lowered.startswith("anonimo+") or "@temp.local" in lowered or "@pronto.local" in lowered:
        return None
    return cleaned


def _resolve_session_customer_email(session) -> str | None:
    email = _normalize_customer_email(session.customer.email if session.customer else None)
    if email:
        return email
    orders = sorted(
        session.orders, key=lambda order: order.created_at or datetime.min, reverse=True
    )
    for order in orders:
        email = _normalize_customer_email(getattr(order, "customer_email", None))
        if email:
            return email
        email = _normalize_customer_email(order.customer.email if order.customer else None)
        if email:
            return email
    return None


@sessions_bp.post("/sessions/<int:session_id>/checkout")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_prepare_checkout(session_id: int):
    """
    Solicitar cuenta (checkout)

    Prepara la sesión para solicitar propina al cliente.
    Accesible por cajeros y meseros.
    """
    response, status = prepare_checkout(session_id)
    return jsonify(response), status


@sessions_bp.post("/sessions/<int:session_id>/tip")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_apply_tip(session_id: int):
    """
    Registrar propina

    Acepta propina fija (tip_amount) o porcentaje (tip_percentage: 5, 10, 15, 20).
    Accesible por cajeros y meseros.

    Body:
        {
            "tip_amount": float (opcional) - Monto fijo de propina
            "tip_percentage": float (opcional) - Porcentaje (5, 10, 15, 20)
        }
    """
    payload = request.get_json(silent=True) or {}
    response, status = apply_tip(
        session_id,
        tip_amount=payload.get("tip_amount"),
        tip_percentage=payload.get("tip_percentage"),
    )
    return jsonify(response), status


@sessions_bp.post("/sessions/<int:session_id>/contact")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_update_contact(session_id: int):
    """
    Actualizar contacto del cliente

    Para compras anónimas, permite actualizar email/teléfono antes o durante el pago.
    Accesible por cajeros y meseros.

    Body:
        {
            "email": str (opcional)
            "phone": str (opcional)
        }
    """
    payload = request.get_json(silent=True) or {}
    response, status = update_customer_contact(
        session_id, email=payload.get("email"), phone=payload.get("phone")
    )
    return jsonify(response), status


@sessions_bp.post("/sessions/<int:session_id>/confirm-payment")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_confirm_payment(session_id: int):
    """
    Confirmar pago pendiente

    Confirma un pago que está en estado awaiting_payment_confirmation.
    Esto cierra la sesión y marca las órdenes como pagadas.
    Solo aplica para métodos de pago que requieren confirmación (efectivo y tarjeta).
    Accesible por cajeros y meseros.

    Body (opcional):
        {
            "order_ids": [int] - IDs de órdenes específicas a pagar (opcional)
                                 Si no se proporciona, se pagan todas las órdenes
        }
    """
    payload = request.get_json(silent=True) or {}
    order_ids = payload.get("order_ids")

    # Si se especifican order_ids, usar pago parcial
    if order_ids is not None:
        if not isinstance(order_ids, list):
            return jsonify({"error": "order_ids debe ser una lista"}), HTTPStatus.BAD_REQUEST

        if not order_ids:
            return jsonify({"error": "order_ids no puede estar vacío"}), HTTPStatus.BAD_REQUEST

        response, status = confirm_partial_payment(session_id, order_ids)
    else:
        # Comportamiento original: pagar todas las órdenes
        response, status = confirm_payment(session_id)

    return jsonify(response), status


@sessions_bp.get("/sessions/<int:session_id>/orders")
@role_required([Roles.CASHIER, Roles.WAITER])
def get_session_orders(session_id: int):
    """
    Obtener todas las órdenes de una sesión para selección de pago

    Retorna información detallada de todas las órdenes de la sesión,
    incluyendo estado de pago y totales individuales.
    Accesible por cajeros y meseros.

    Returns:
        {
            "session_id": int,
            "table_number": str,
            "orders": [
                {
                    "id": int,
                    "workflow_status": str,
                    "payment_status": str,
                    "total_amount": float,
                    "items_count": int,
                    "customer_name": str,
                    "created_at": str
                }
            ]
        }
    """
    from sqlalchemy.orm import joinedload

    from shared.db import get_session as get_db_session
    from shared.models import DiningSession, Order

    with get_db_session() as db_session:
        dining_session = (
            db_session.execute(
                select(DiningSession)
                .options(
                    joinedload(DiningSession.orders).joinedload(Order.items),
                    joinedload(DiningSession.orders).joinedload(Order.customer),
                    joinedload(DiningSession.table),
                )
                .where(DiningSession.id == session_id)
            )
            .unique()
            .scalars()
            .first()
        )

        if not dining_session:
            return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

        orders_data = []
        for order in dining_session.orders:
            orders_data.append(
                {
                    "id": order.id,
                    "workflow_status": order.workflow_status,
                    "payment_status": order.payment_status,
                    "total_amount": float(order.total_amount),
                    "items_count": len(order.items),
                    "customer_name": order.customer.name if order.customer else "Cliente",
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "is_paid": order.payment_status == "paid",
                }
            )

        return jsonify(
            {
                "session_id": dining_session.id,
                "table_number": dining_session.table_number
                or (dining_session.table.table_number if dining_session.table else "N/A"),
                "orders": orders_data,
                "total_orders": len(orders_data),
                "unpaid_orders": sum(1 for o in orders_data if not o["is_paid"]),
            }
        ), HTTPStatus.OK


@sessions_bp.post("/sessions/<int:session_id>/pay")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_finalize_payment(session_id: int):
    """
    Procesar pago

    Finaliza el pago de una sesión. Opcionalmente acepta propina y contacto del cliente
    para compras anónimas.
    Accesible por cajeros y meseros.

    Validaciones:
    - session_id debe ser positivo
    - tip_amount debe estar entre 0 y 10000
    - tip_percentage debe estar entre 0 y 100
    - payment_method se valida en la capa de servicio

    Body:
        {
            "payment_method": str - "cash" o "clip" (default: "cash")
            "tip_amount": float (opcional) - Monto fijo de propina
            "tip_percentage": float (opcional) - Porcentaje de propina
            "payment_reference": str (opcional) - Referencia de pago (para Clip)
            "customer_email": str (opcional) - Email del cliente (anónimo)
            "customer_phone": str (opcional) - Teléfono del cliente (anónimo)
        }
    """
    if session_id <= 0:
        return jsonify({"error": "ID de sesión inválido"}), HTTPStatus.BAD_REQUEST

    payload = request.get_json(silent=True) or {}

    # Validate tip_amount
    tip_amount = payload.get("tip_amount")
    if tip_amount is not None:
        try:
            tip_amount = float(tip_amount)
            if tip_amount < 0 or tip_amount > 10000:
                return jsonify(
                    {"error": "Monto de propina inválido (0-10000)"}
                ), HTTPStatus.BAD_REQUEST
        except (ValueError, TypeError):
            return jsonify({"error": "Monto de propina debe ser un número"}), HTTPStatus.BAD_REQUEST

    # Validate tip_percentage
    tip_percentage = payload.get("tip_percentage")
    if tip_percentage is not None:
        try:
            tip_percentage = float(tip_percentage)
            if tip_percentage < 0 or tip_percentage > 100:
                return jsonify(
                    {"error": "Porcentaje de propina inválido (0-100)"}
                ), HTTPStatus.BAD_REQUEST
        except (ValueError, TypeError):
            return jsonify(
                {"error": "Porcentaje de propina debe ser un número"}
            ), HTTPStatus.BAD_REQUEST

    response, status = finalize_payment(
        session_id,
        payment_method=payload.get("payment_method", "cash"),
        tip_amount=tip_amount,
        tip_percentage=tip_percentage,
        payment_reference=payload.get("payment_reference"),
        customer_email=payload.get("customer_email"),
        customer_phone=payload.get("customer_phone"),
    )

    if status == 200:
        audit_action(
            "PAYMENT_SUCCESS",
            f"Session {session_id} paid. Method: {payload.get('payment_method', 'cash')}",
            "OK",
        )
    else:
        audit_action("PAYMENT_FAIL", f"Session {session_id} payment error", "ERROR")

    return jsonify(response), status


@sessions_bp.get("/sessions/<int:session_id>/ticket")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN])
def get_ticket(session_id: int):
    """
    Obtener ticket de una sesión

    Genera el ticket fiscal de una sesión cerrada.
    """
    ticket, status = generate_ticket(session_id)
    if status != 200:
        return jsonify({"error": ticket}), status
    return jsonify({"ticket": ticket}), status


@sessions_bp.get("/sessions/closed")
@role_required([Roles.CASHIER, Roles.SUPER_ADMIN, Roles.ADMIN])
def get_closed_sessions():
    """
    Obtener historial de sesiones cerradas

    Lista las sesiones cerradas dentro del período configurado (default: 24 horas).
    SOLO accesible por cajeros.

    Query params:
        - hours: int (opcional) - Número de horas hacia atrás
    """
    hours = request.args.get("hours", type=int)
    response, status = list_closed_sessions(hours)
    return jsonify(response), status


@sessions_bp.get("/sessions/paid-recent")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER, Roles.CHEF])
def get_paid_recent_sessions():
    """
    Obtener sesiones pagadas de hoy

    Lista las sesiones cerradas/pagadas del día de hoy.
    Accesible por meseros, cajeros y administradores.

    Query params:
        - waiter_id: int (opcional) - Filtrar por mesero específico
    """
    from datetime import datetime

    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from shared.db import get_session
    from shared.models import DiningSession, Order

    def safe_float(value: float | None) -> float:
        try:
            return float(value) if value is not None else 0.0
        except Exception:
            return 0.0

    try:
        waiter_id = request.args.get("waiter_id", type=int)

        with get_session() as db:
            # Get business timezone
            import pytz

            from shared.models import BusinessInfo

            business_info = db.execute(select(BusinessInfo).limit(1)).scalar_one_or_none()
            tz_name = (
                business_info.timezone
                if business_info and business_info.timezone
                else "America/Mexico_City"
            )
            business_tz = pytz.timezone(tz_name)

            # Get sessions from today (start of day in business timezone)
            now_business = datetime.now(business_tz)
            today_start_business = now_business.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start = today_start_business.astimezone(pytz.UTC).replace(tzinfo=None)

            # Build query for paid/paid sessions from today
            stmt = (
                select(DiningSession)
                .options(
                    joinedload(DiningSession.customer),
                    joinedload(DiningSession.orders).joinedload(Order.items),
                    joinedload(DiningSession.orders).joinedload(Order.waiter),
                )
                .where(
                    DiningSession.status.in_([SessionStatus.PAID.value, SessionStatus.PAID.value]),
                    DiningSession.closed_at >= today_start,
                )
                .order_by(DiningSession.closed_at.desc())
            )

            sessions = db.execute(stmt).unique().scalars().all()

            sessions_data = []
            for session in sessions:
                try:
                    # If waiter_id filter is provided, check if any order belongs to that waiter
                    if waiter_id:
                        has_waiter_order = any(o.waiter_id == waiter_id for o in session.orders)
                        if not has_waiter_order:
                            continue

                    # Get waiter name from first order (if available)
                    waiter_name = None
                    for order in session.orders:
                        if order.waiter and order.waiter.name:
                            waiter_name = order.waiter.name
                            break

                    closed_at = (
                        session.closed_at
                        or session.payment_confirmed_at
                        or session.updated_at
                        or datetime.utcnow()
                    )

                    resolved_email = _resolve_session_customer_email(session)
                    customer_name = session.customer.name if session.customer else "Cliente"
                    customer_name_upper = (customer_name or "").upper()
                    if resolved_email and (
                        not customer_name
                        or customer_name_upper
                        in {
                            "INVITADO",
                            "CLIENTE ANONIMO",
                            "CLIENTE ANÓNIMO",
                            "ANONIMO",
                            "ANÓNIMO",
                            "CLIENTE",
                        }
                    ):
                        customer_name = resolved_email

                    sessions_data.append(
                        {
                            "id": session.id,
                            "customer_name": customer_name,
                            "customer_email": resolved_email,
                            "table_number": session.table_number,
                            "status": session.status,
                            "closed_at": closed_at.isoformat() if closed_at else None,
                            "payment_method": session.payment_method,
                            "subtotal": safe_float(session.subtotal),
                            "tax_amount": safe_float(session.tax_amount),
                            "tip_amount": safe_float(session.tip_amount),
                            "total_amount": safe_float(session.total_amount),
                            "waiter_name": waiter_name,
                            "orders_count": len(session.orders),
                            "order_ids": sorted([order.id for order in session.orders]),
                        }
                    )
                except Exception as ser_err:
                    logger.error(
                        "Error serializando sesión pagada %s: %s",
                        session.id,
                        ser_err,
                        exc_info=True,
                    )
                    continue

            return jsonify({"sessions": sessions_data, "count": len(sessions_data)}), HTTPStatus.OK

    except Exception as e:
        import traceback

        logger.error(f"Error getting paid sessions: {e!s}", exc_info=True)
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@sessions_bp.post("/sessions/<int:session_id>/reprint")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_reprint_ticket(session_id: int):
    """
    Reimprimir ticket

    Genera nuevamente el ticket de una sesión cerrada para reimpresión.
    SOLO accesible por cajeros.

    Query params:
        - format: "text" (default) o "pdf" para generar PDF descargable
    """
    output_format = request.args.get("format", "text").lower()

    if output_format == "pdf":
        from shared.services.ticket_pdf_service import generate_ticket_pdf

        pdf_bytes, status, error = generate_ticket_pdf(session_id)
        if error:
            return jsonify({"error": error}), status

        filename = f"ticket_{session_id}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(pdf_bytes)),
            },
        )

    # Default: text format
    ticket, status = generate_ticket(session_id)
    if status != 200:
        return jsonify({"error": ticket}), status
    return jsonify({"ticket": ticket, "message": "Ticket generado para impresión"}), status


@sessions_bp.get("/sessions/<int:session_id>/ticket.pdf")
@role_required([Roles.CASHIER, Roles.WAITER])
def get_ticket_pdf(session_id: int):
    """
    Descargar ticket en PDF

    Genera y descarga el ticket de una sesión en formato PDF.
    SOLO accesible por cajeros.

    Returns:
        PDF file as attachment
    """
    from shared.services.ticket_pdf_service import generate_ticket_pdf

    pdf_bytes, status, error = generate_ticket_pdf(session_id)
    if error:
        return jsonify({"error": error}), status

    filename = f"ticket_{session_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@sessions_bp.get("/sessions/awaiting-payment")
@role_required(Roles.CASHIER)
def get_sessions_awaiting_payment():
    """
    Obtener sesiones pendientes de pago

    Lista las sesiones que han solicitado la cuenta (check_requested_at no es NULL)
    y aún no están cerradas. Estas son las sesiones listas para que el cajero procese el pago.
    SOLO accesible por cajeros.

    Returns:
        Lista de sesiones con sus órdenes, ordenadas por check_requested_at (más recientes primero)
    """
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from shared.db import get_session
    from shared.models import DiningSession, Order

    try:
        with get_session() as db:
            # Get sessions that have requested check but are not closed
            stmt = (
                select(DiningSession)
                .options(
                    joinedload(DiningSession.customer),
                    joinedload(DiningSession.orders).joinedload(Order.items),
                )
                .where(
                    DiningSession.check_requested_at.isnot(None),
                    DiningSession.status != SessionStatus.PAID.value,
                )
                .order_by(DiningSession.check_requested_at.desc())
            )

            sessions = db.execute(stmt).unique().scalars().all()

            sessions_data = []
            for session in sessions:
                # Get delivered orders count
                delivered_orders = [
                    o for o in session.orders if o.workflow_status == OrderStatus.DELIVERED.value
                ]
                customer_name = session.customer.name if session.customer else ""
                customer_email = _resolve_session_customer_email(session) or ""
                customer_name_upper = (customer_name or "").upper()
                if customer_email and (
                    not customer_name
                    or customer_name_upper
                    in {
                        "INVITADO",
                        "CLIENTE ANONIMO",
                        "CLIENTE ANÓNIMO",
                        "ANONIMO",
                        "ANÓNIMO",
                        "CLIENTE",
                    }
                ):
                    customer_display_name = customer_email
                elif customer_name:
                    customer_display_name = customer_name
                else:
                    customer_display_name = "Cliente"

                sessions_data.append(
                    {
                        "id": session.id,
                        "customer_name": customer_display_name,
                        "customer_email": customer_email or None,
                        "table_number": session.table_number,
                        "status": session.status,
                        "check_requested_at": session.check_requested_at.isoformat()
                        if session.check_requested_at
                        else None,
                        "subtotal": float(session.subtotal),
                        "tax_amount": float(session.tax_amount),
                        "tip_amount": float(session.tip_amount),
                        "total_amount": float(session.total_amount),
                        "orders_count": len(session.orders),
                        "delivered_orders_count": len(delivered_orders),
                    }
                )

            return jsonify({"sessions": sessions_data, "count": len(sessions_data)}), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching sessions awaiting payment: {e}")
        return jsonify(
            error_response("Error al obtener sesiones pendientes de pago")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.get("/sessions/pending")
@role_required([Roles.CASHIER, Roles.WAITER])
def get_pending_sessions():
    """
    Endpoint de compatibilidad para sesiones pendientes.
    Retorna las mismas que awaiting-payment (o vacío si hay error) para no romper la UI.
    """
    try:
        data, status = get_sessions_awaiting_payment()
        # get_sessions_awaiting_payment ya devuelve Response; si es tuple lo respetamos
        return data, status  # type: ignore
    except Exception:
        return jsonify({"sessions": [], "count": 0}), HTTPStatus.OK


@sessions_bp.post("/sessions/<int:session_id>/resend")
@role_required([Roles.CASHIER, Roles.WAITER])
def post_resend_ticket(session_id: int):
    """
    Reenviar ticket por email

    Envía el ticket de una sesión cerrada al email del cliente.
    SOLO accesible por cajeros.

    Body:
        {
            "email": str - Email del destinatario
        }
    """
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not email:
        return jsonify({"error": "Email es requerido"}), HTTPStatus.BAD_REQUEST

    response, status = resend_ticket(session_id, email)
    return jsonify(response), status


@sessions_bp.get("/sessions/all")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.CASHIER, Roles.WAITER, Roles.CHEF])
def get_all_sessions():
    """
    Obtener todas las sesiones

    Lista todas las sesiones activas con información detallada incluyendo:
    - Mesa
    - Fecha de inicio
    - Fecha de última orden
    - Cantidad de órdenes activas
    Accesible por cajeros y administradores.

    Query params:
        - include_paid: bool (opcional) - Incluir sesiones pagadas (default: False)
    """
    include_paid = request.args.get("include_paid", "false").lower() == "true"
    response, status = list_all_sessions(include_paid=include_paid)
    return jsonify(response), status


@sessions_bp.post("/sessions/<int:session_id>/close")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN])
def post_close_session(session_id: int):
    """
    Cerrar sesión

    Cierra una sesión y cancela todas sus órdenes activas.
    Útil para limpiar sesiones duplicadas o sesiones sin actividad.
    Accesible por cajeros y administradores.
    """
    response, status = close_session(session_id)
    return jsonify(response), status


# ============================================================================
# Anonymous Sessions Management
# ============================================================================


@sessions_bp.get("/sessions/anonymous")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN])
def get_anonymous_sessions():
    """
    Lista todas las sesiones anónimas activas (no cerradas/pagadas).
    Ordena por mesa y marca las mesas con múltiples sesiones.
    """
    from collections import Counter

    from sqlalchemy import func, select

    from shared.db import get_session
    from shared.models import Customer, DiningSession, Order

    try:
        with get_session() as db_session:
            # Get all sessions with anonymous customers (email starts with 'anonimo+')
            # that are not closed/paid
            active_statuses = [
                "open",
                "awaiting_tip",
                "awaiting_payment",
                "awaiting_payment_confirmation",
            ]

            # Get all active sessions with customers, then filter by email in Python
            # (email is encrypted so we can't use LIKE in SQL)
            all_sessions = (
                db_session.execute(
                    select(DiningSession)
                    .join(Customer, DiningSession.customer_id == Customer.id, isouter=True)
                    .where(DiningSession.status.in_(active_statuses))
                    .order_by(DiningSession.table_number, DiningSession.opened_at.desc())
                )
                .scalars()
                .all()
            )

            def is_anonymous_customer(customer) -> bool:
                if not customer:
                    return False
                try:
                    email = (customer.email or "").lower()
                except Exception as exc:
                    logger.warning("Failed to read customer email for anonymous check: %s", exc)
                    email = ""
                if email.startswith("anonimo+"):
                    return True
                try:
                    name = (customer.name or "").strip().upper()
                except Exception as exc:
                    logger.warning("Failed to read customer name for anonymous check: %s", exc)
                    name = ""
                return name in {
                    "INVITADO",
                    "CLIENTE ANONIMO",
                    "CLIENTE ANÓNIMO",
                    "ANONIMO",
                    "ANÓNIMO",
                    "CLIENTE",
                }

            # Filter sessions with anonymous customers
            sessions = [sess for sess in all_sessions if is_anonymous_customer(sess.customer)]

            # Count sessions per table to detect duplicates
            table_counts = Counter(sess.table_number for sess in sessions if sess.table_number)

            sessions_data = []
            for sess in sessions:
                # Count orders for this session
                orders_count = (
                    db_session.execute(
                        select(func.count(Order.id)).where(Order.session_id == sess.id)
                    ).scalar()
                    or 0
                )

                # Extract anonymous client ID from email
                anon_id = None
                email = ""
                if sess.customer:
                    try:
                        email = sess.customer.email or ""
                    except Exception as exc:
                        logger.warning("Failed to read customer email for anonymous id: %s", exc)
                        email = ""
                if email.startswith("anonimo+"):
                    anon_id = email.split("@")[0].replace("anonimo+", "")

                # Check if this table has multiple sessions (duplicate)
                table_num = sess.table_number or ""
                is_duplicate = table_counts.get(table_num, 0) > 1

                sessions_data.append(
                    {
                        "id": sess.id,
                        "table_number": sess.table_number,
                        "anonymous_client_id": anon_id,
                        "status": sess.status,
                        "orders_count": orders_count,
                        "created_at": sess.opened_at.isoformat() if sess.opened_at else None,
                        "customer_name": sess.customer.name if sess.customer else None,
                        "is_duplicate_table": is_duplicate,
                    }
                )

            # Get list of tables with duplicates
            duplicate_tables = [table for table, count in table_counts.items() if count > 1]

            return jsonify(
                {
                    "sessions": sessions_data,
                    "count": len(sessions_data),
                    "duplicate_tables": duplicate_tables,
                    "duplicate_count": len(duplicate_tables),
                }
            )
    except Exception as e:
        logger.error(f"Error getting anonymous sessions: {e}", exc_info=True)
        return jsonify(
            {
                "sessions": [],
                "count": 0,
                "duplicate_tables": [],
                "duplicate_count": 0,
                "error": "Error al obtener sesiones anónimas",
            }
        ), HTTPStatus.OK


@sessions_bp.delete("/sessions/<int:session_id>/anonymous")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN])
def delete_anonymous_session(session_id: int):
    """
    Elimina una sesión anónima (cierra la sesión y limpia datos).
    Solo funciona si la sesión no tiene órdenes con items pagados.
    """
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify(error_response("Sesión no encontrada")), HTTPStatus.NOT_FOUND

            # Check if session has any paid orders
            orders = (
                db_session.execute(select(Order).where(Order.session_id == session_id))
                .scalars()
                .all()
            )

            has_paid_orders = any(o.payment_status == "paid" for o in orders)
            if has_paid_orders:
                return jsonify(
                    error_response("No se puede eliminar: la sesión tiene órdenes pagadas")
                ), HTTPStatus.BAD_REQUEST

            # Delete order items and orders
            for order in orders:
                for item in order.items:
                    db_session.delete(item)
                db_session.delete(order)

            # Mark session as cancelled instead of deleting
            dining_session.status = "cancelled"
            db_session.commit()

            return jsonify(
                {"status": "success", "message": "Sesión anónima eliminada correctamente"}
            )
    except Exception as e:
        logger.error(f"Error deleting anonymous session: {e}", exc_info=True)
        return jsonify(
            error_response("Error al eliminar sesión anónima")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.post("/sessions/<int:session_id>/regenerate-anonymous")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN])
def regenerate_anonymous_session(session_id: int):
    """
    Regenera el ID de cliente anónimo para una sesión.
    Crea un nuevo cliente anónimo y reasigna la sesión y sus órdenes.
    """
    import uuid

    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import Customer, DiningSession, Order

    try:
        with get_session() as db_session:
            dining_session = (
                db_session.execute(select(DiningSession).where(DiningSession.id == session_id))
                .scalars()
                .one_or_none()
            )

            if not dining_session:
                return jsonify(error_response("Sesión no encontrada")), HTTPStatus.NOT_FOUND

            # Generate new anonymous client ID
            new_anon_id = str(uuid.uuid4())[:8]
            new_email = f"anonimo+{new_anon_id}@pronto.local"

            # Create new anonymous customer
            new_customer = Customer(name="Cliente Anónimo", email=new_email)
            db_session.add(new_customer)
            db_session.flush()  # Get the new customer ID

            # Update session with new customer
            dining_session.customer_id = new_customer.id

            # Update all orders in this session
            orders = (
                db_session.execute(select(Order).where(Order.session_id == session_id))
                .scalars()
                .all()
            )

            for order in orders:
                order.customer_id = new_customer.id

            db_session.commit()

            return jsonify(
                {
                    "status": "success",
                    "message": "ID de cliente anónimo regenerado",
                    "new_anonymous_id": new_anon_id,
                    "session_id": session_id,
                }
            )
    except Exception as e:
        logger.error(f"Error regenerating anonymous session: {e}", exc_info=True)
        return jsonify(
            error_response("Error al regenerar sesión anónima")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.post("/sessions/clean-inactive")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN])
def clean_inactive_sessions():
    """
    Limpiar sesiones inactivas

    Elimina sesiones anónimas que:
    - No tienen órdenes asociadas, O
    - Fueron creadas hace más de 24 horas

    SOLO accesible por administradores.

    Returns:
        Número de sesiones eliminadas
    """
    try:
        from datetime import timedelta

        from shared.db import get_session
        from shared.models import Customer, Order, Session

        with get_session() as db_session:
            # Calcular fecha límite (24 horas atrás)
            cutoff_time = datetime.now() - timedelta(hours=24)

            # Buscar sesiones anónimas inactivas
            sessions_to_delete = (
                db_session.execute(
                    select(Session)
                    .outerjoin(Order, Session.id == Order.session_id)
                    .join(Customer, Session.customer_id == Customer.id)
                    .where(
                        (Customer.email.like("%@temp.local%"))  # Clientes anónimos
                        | (Customer.email.like("%@pronto.local%"))
                        | (Customer.email.like("anonimo+%"))
                    )
                    .where(
                        (Order.id.is_(None))  # Sin órdenes
                        | (Session.created_at < cutoff_time)  # O más de 24h
                    )
                    .where(Session.status != SessionStatus.CLOSED)  # No cerradas
                )
                .scalars()
                .all()
            )

            count = len(sessions_to_delete)

            # Eliminar sesiones
            for session in sessions_to_delete:
                db_session.delete(session)

            db_session.commit()

            logger.info(f"Cleaned {count} inactive anonymous sessions")

            return jsonify(
                {
                    "status": "success",
                    "message": f"{count} sesiones inactivas eliminadas",
                    "count": count,
                }
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error cleaning inactive sessions: {e}", exc_info=True)
        return jsonify(
            error_response("Error al limpiar sesiones inactivas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.post("/sessions/clean-all")
@role_required([Roles.SUPER_ADMIN])
def clean_all_sessions():
    """
    Limpiar TODAS las sesiones

    Elimina TODAS las sesiones que no estén cerradas.
    USAR CON EXTREMA PRECAUCIÓN - Solo para Super Admin.

    Returns:
        Número de sesiones eliminadas
    """
    try:
        from shared.db import get_session
        from shared.models import Session

        with get_session() as db_session:
            # Buscar todas las sesiones no cerradas
            sessions_to_delete = (
                db_session.execute(select(Session).where(Session.status != SessionStatus.CLOSED))
                .scalars()
                .all()
            )

            count = len(sessions_to_delete)

            # Eliminar sesiones
            for session in sessions_to_delete:
                db_session.delete(session)

            db_session.commit()

            logger.warning(f"CLEANED ALL SESSIONS: {count} sessions deleted by admin")

            return jsonify(
                {"status": "success", "message": f"{count} sesiones eliminadas", "count": count}
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error cleaning all sessions: {e}", exc_info=True)
        return jsonify(
            error_response("Error al limpiar todas las sesiones")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.get("/paid")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.ADMIN])
def get_paid_sessions():
    """
    Get list of paid sessions (completed orders) for cashier dashboard.

    Returns sessions with status 'paid' including their orders and ticket info.
    Can be used to generate PDFs or resend emails.

    Query params:
        - hours: Number of hours to look back (default 24)

    Returns:
        List of paid sessions with actions available (resend_email, download_pdf)
    """
    from datetime import timedelta

    from sqlalchemy.orm import joinedload

    from shared.db import get_session as get_db_session
    from shared.models import DiningSession, Order

    hours = int(request.args.get("hours", 24))
    since = datetime.utcnow() - timedelta(hours=hours)

    try:
        with get_db_session() as session:
            paid_sessions = (
                session.execute(
                    select(DiningSession)
                    .options(
                        joinedload(DiningSession.orders).joinedload(Order.items),
                        joinedload(DiningSession.customer),
                        joinedload(DiningSession.table),
                    )
                    .where(
                        DiningSession.status == SessionStatus.PAID.value,
                        DiningSession.closed_at >= since,
                    )
                    .order_by(DiningSession.closed_at.desc())
                    .limit(100)
                )
                .unique()
                .scalars()
                .all()
            )

            sessions_data = []
            for ds in paid_sessions:
                # Check if email is available for resending
                from shared.services.order_service import resolve_session_customer_email

                customer_email = resolve_session_customer_email(ds)

                sessions_data.append(
                    {
                        "id": ds.id,
                        "table_number": ds.table_number
                        or (ds.table.table_number if ds.table else None),
                        "customer_name": ds.customer.name if ds.customer else "Anónimo",
                        "customer_email": customer_email,
                        "total_amount": float(ds.total_amount),
                        "paid_at": ds.closed_at.isoformat() if ds.closed_at else None,
                        "payment_method": ds.payment_method,
                        "orders_count": len(ds.orders),
                        "actions": {
                            "resend_email": bool(customer_email),
                            "download_pdf": True,
                        },
                    }
                )

            return jsonify({"sessions": sessions_data, "count": len(sessions_data)}), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching paid sessions: {e}", exc_info=True)
        return jsonify(
            error_response("Error al obtener sesiones pagadas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@sessions_bp.post("/sessions/<int:session_id>/send-ticket-email")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.ADMIN])
def send_ticket_email_endpoint(session_id: int):
    """
    Send ticket email for a paid session (from cashier dashboard).

    Allows resending ticket emails for completed payments from the cashier's paid orders tab.

    Args:
        session_id: Dining session ID

    Body (optional):
        - email: Override email address (optional)

    Returns:
        Success message if email sent
    """
    from shared.db import get_session as get_db_session
    from shared.models import DiningSession
    from shared.services.order_service import resend_ticket

    payload = request.get_json(silent=True) or {}
    override_email = payload.get("email")

    with get_db_session() as session:
        dining_session = session.get(DiningSession, session_id)
        if not dining_session:
            return jsonify({"error": "Cuenta no encontrada"}), HTTPStatus.NOT_FOUND

        if dining_session.status != SessionStatus.PAID.value:
            return jsonify(
                {"error": "Solo se pueden enviar tickets de cuentas pagadas"}
            ), HTTPStatus.BAD_REQUEST

        # Use override email or get from session
        email_to_send = override_email
        if not email_to_send:
            from shared.services.order_service import resolve_session_customer_email

            email_to_send = resolve_session_customer_email(dining_session)

        if not email_to_send:
            return jsonify(
                {"error": "No hay email disponible para esta cuenta"}
            ), HTTPStatus.BAD_REQUEST

    # Send the ticket
    response, status = resend_ticket(session_id, email_to_send)
    return jsonify(response), status


@sessions_bp.get("/sessions/<int:session_id>/ticket.pdf")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.ADMIN])
def get_ticket_pdf_paid(session_id: int):
    """
    Generate and download PDF ticket for a paid session.

    Allows downloading PDF tickets from cashier dashboard for completed payments.

    Args:
        session_id: Dining session ID

    Returns:
        PDF file as download
    """
    from shared.services.ticket_pdf_service import generate_ticket_pdf

    pdf_bytes, status, error = generate_ticket_pdf(session_id)

    if status != HTTPStatus.OK or not pdf_bytes:
        return jsonify({"error": error or "Error generando PDF"}), status

    filename = f"ticket_session_{session_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
