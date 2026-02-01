"""
Orders API - Endpoints para gestión de órdenes
Handles all order workflow actions: accept, kitchen operations, delivery, cancellation, modifications
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy.orm import joinedload

from employees_app.decorators import login_required, role_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.constants import ModificationInitiator, OrderStatus, Roles
from shared.db import get_session as get_db_session
from shared.models import Order
from shared.services.order_modification_service import create_modification
from shared.services.order_service import (
    accept_or_queue,
    cancel_order,
    deliver_order,
    deliver_order_items,
    get_order_delivery_status,
    kitchen_complete,
    kitchen_start,
    list_orders,
    mark_awaiting_payment,
    pay_order,
    update_order_notes,
    waiter_accept,
)
from shared.supabase.realtime import emit_order_status_change

# Create blueprint without url_prefix (inherited from parent)
orders_bp = Blueprint("orders", __name__)


@orders_bp.get("/orders")
@jwt_required
def get_orders():
    """
    Lista todas las órdenes activas con soporte de paginación
    """
    include_closed = request.args.get("include_closed", "false").lower() in {"1", "true", "yes"}
    include_delivered = request.args.get("include_delivered", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 50, type=int)

    result = list_orders(
        include_closed=include_closed, include_delivered=include_delivered, page=page, limit=limit
    )
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@orders_bp.get("/orders/kitchen/pending")
@role_required([Roles.CHEF, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.WAITER])
def get_kitchen_pending_orders():
    """
    Lista las órdenes pendientes en cocina (para el panel de cocina)
    """
    # Filtrar solo órdenes que están en cocina o pendientes de cocina
    result = list_orders(include_closed=False, include_delivered=False)
    all_orders = result.get("orders", [])
    kitchen_orders = [
        order
        for order in all_orders
        if order.get("requires_kitchen")
        and order.get("workflow_status")
        in [
            OrderStatus.QUEUED.value,
            OrderStatus.PREPARING.value,
            OrderStatus.READY.value,
        ]
    ]
    response = jsonify({"orders": kitchen_orders})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@orders_bp.post("/orders/<int:order_id>/accept")
@role_required([Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_waiter_accept(order_id: int):
    """
    Aceptar una orden (mesero)
    """
    employee_id = get_employee_id()
    response, status = waiter_accept(order_id, employee_id)

    # Emit evento Redis si la operación fue exitosa
    if status == 200:
        with get_db_session() as db:
            order = (
                db.query(Order)
                .options(joinedload(Order.session))
                .filter(Order.id == order_id)
                .first()
            )
            if order:
                emit_order_status_change(
                    order_id=order.id,
                    status=order.workflow_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/kitchen/start")
@role_required([Roles.CHEF, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_chef_start(order_id: int):
    """
    Iniciar preparación en cocina
    """
    employee_id = get_employee_id()
    user = get_current_user()
    actor_scope = user.get("active_scope", "chef")
    response, status = kitchen_start(order_id, employee_id, actor_scope=actor_scope)

    # Emit evento Redis si la operación fue exitosa
    if status == 200:
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                emit_order_status_change(
                    order_id=order.id,
                    status=order.workflow_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/kitchen/ready")
@role_required([Roles.CHEF, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_chef_ready(order_id: int):
    """
    Marcar orden como lista para entrega
    """
    user = get_current_user()
    actor_scope = user.get("active_scope", "chef")
    response, status = kitchen_complete(order_id, actor_scope=actor_scope)

    # Emit evento Redis si la operación fue exitosa
    if status == 200:
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                emit_order_status_change(
                    order_id=order.id,
                    status=order.workflow_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/deliver")
@role_required([Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_deliver_order(order_id: int):
    """
    Marcar orden como entregada al cliente

    Body:
        {
            "employee_id": int  # ID del mesero que entrega
        }
    """
    employee_id = get_employee_id()
    response, status = deliver_order(order_id, employee_id)

    # Emit evento Redis si la operación fue exitosa
    if status == 200:
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                emit_order_status_change(
                    order_id=order.id,
                    status=order.workflow_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/awaiting-payment")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_mark_awaiting_payment(order_id: int):
    user = get_current_user()
    actor_scope = user.get("active_scope", "cashier")
    response, status = mark_awaiting_payment(order_id, actor_scope=actor_scope)
    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/pay")
@role_required([Roles.CASHIER, Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_pay_order(order_id: int):
    payload = request.get_json(silent=True) or {}
    user = get_current_user()
    actor_scope = user.get("active_scope", "cashier")
    response, status = pay_order(
        order_id=order_id,
        payment_method=payload.get("payment_method"),
        actor_scope=actor_scope,
        payment_reference=payload.get("payment_reference"),
        payment_meta=payload.get("payment_meta"),
        justification=payload.get("justification"),
    )
    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/cancel")
@jwt_required
def post_cancel_order(order_id: int):
    """
    Cancelar una orden

    Requiere autenticación. El actor se determina por el rol del empleado en sesión.
    """
    payload = request.get_json(silent=True) or {}
    reason = payload.get("cancellation_reason") or payload.get("reason")
    user = get_current_user()
    actor_scope = user.get("active_scope", "employee")
    employee_id = get_employee_id()
    response, status = cancel_order(
        order_id,
        actor_scope=actor_scope,
        actor_id=employee_id,
        reason=reason,
    )

    if status == 200:
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                emit_order_status_change(
                    order_id=order.id,
                    status=order.workflow_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/modify")
@jwt_required
def post_modify_order_waiter(order_id: int):
    """
    Modificar una orden (mesero)

    Permite a los meseros modificar órdenes en cualquier momento (requiere aprobación del cliente).

    Body:
        {
            "changes": {
                "items_to_add": [{"menu_item_id": 1, "quantity": 2, "modifiers": [...]}],
                "items_to_remove": [order_item_id1, order_item_id2],
                "items_to_update": [{"order_item_id": 3, "quantity": 5}],
                "reason": "Customer requested changes" (optional)
            }
        }
    """
    employee_id = get_employee_id()
    if not employee_id:
        return jsonify({"error": "No autenticado"}), HTTPStatus.UNAUTHORIZED

    payload = request.get_json(silent=True) or {}
    changes = payload.get("changes")

    if not changes or not isinstance(changes, dict):
        return jsonify(
            {"error": "changes es requerido y debe ser un objeto"}
        ), HTTPStatus.BAD_REQUEST

    response, status = create_modification(
        order_id=order_id,
        changes_data=changes,
        initiated_by_role=ModificationInitiator.WAITER.value,
        employee_id=employee_id,
    )

    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/notes")
@jwt_required
def post_order_notes(order_id: int):
    """
    Actualizar notas de una orden

    Permite a los meseros agregar anotaciones a una orden.

    Body:
        {
            "notes": str  # Notas del mesero
        }
    """
    payload = request.get_json(silent=True) or {}
    employee_id = get_employee_id()

    response, status = update_order_notes(order_id, payload.get("notes"), employee_id)
    return jsonify(response), status


@orders_bp.post("/orders/<int:order_id>/deliver-items")
@role_required([Roles.WAITER, Roles.SUPER_ADMIN, Roles.ADMIN_ROLES])
def post_deliver_order_items(order_id: int):
    """
    Entregar items específicos de una orden (entrega parcial)

    Body:
        {
            "item_ids": [int],  # Lista de IDs de OrderItem a entregar
            "employee_id": int  # ID del mesero que entrega
        }

    Returns:
        {
            "id": int,
            "workflow_status": str,
            "items": [
                {
                    "id": int,
                    "delivered_quantity": int,
                    "is_fully_delivered": bool,
                    ...
                }
            ],
            ...
        }
    """
    payload = request.get_json(silent=True) or {}
    item_ids = payload.get("item_ids", [])
    employee_id = payload.get("employee_id")

    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids debe ser una lista"}), HTTPStatus.BAD_REQUEST

    response, status = deliver_order_items(order_id, item_ids, employee_id)

    # Emit evento Redis si la operación fue exitosa
    if status == 200:
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                # Verificar si todos los items fueron entregados
                all_delivered = all(item.is_fully_delivered for item in order.items)
                emit_status = "delivered" if all_delivered else "partial_delivery"

                emit_order_status_change(
                    order_id=order.id,
                    status=emit_status,
                    session_id=order.session_id,
                    table_number=order.session.table_number if order.session else None,
                )

    return jsonify(response), status


@orders_bp.get("/orders/<int:order_id>/delivery-status")
@jwt_required
def get_order_delivery_status_endpoint(order_id: int):
    """
    Obtener el estado de entrega de todos los items de una orden

    Returns:
        {
            "order_id": int,
            "workflow_status": str,
            "items": [
                {
                    "id": int,
                    "menu_item_id": int,
                    "menu_item_name": str,
                    "quantity": int,
                    "delivered_quantity": int,
                    "is_fully_delivered": bool,
                    "delivered_at": str | null,
                    "delivered_by_employee_id": int | null
                }
            ],
            "all_items_delivered": bool
        }
    """
    response, status = get_order_delivery_status(order_id)
    resp = jsonify(response)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp, status


@orders_bp.post("/orders/table-rows")
@jwt_required
def get_new_order_rows():
    """
    Obtener HTML de filas de tabla para órdenes nuevas

    Body:
        {
            "existing_order_ids": [int]  # Lista de IDs de órdenes que ya tienen fila en el DOM
        }

    Returns:
        {
            "html": str,  # HTML de las filas nuevas
            "new_order_ids": [int]  # IDs de las órdenes nuevas
        }
    """
    from flask import render_template

    payload = request.get_json(silent=True) or {}
    existing_order_ids = set(payload.get("existing_order_ids", []))

    # Get all orders
    include_closed = request.args.get("include_closed", "false").lower() in {"1", "true", "yes"}
    include_delivered = request.args.get("include_delivered", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    all_orders = list_orders(include_closed=include_closed, include_delivered=include_delivered)

    # Filter to only new orders (those not in existing_order_ids)
    new_orders = [order for order in all_orders if order["id"] not in existing_order_ids]

    # Render HTML for new orders
    html_parts = []
    new_order_ids = []

    for order_data in new_orders:
        # Convert dict to object-like structure for template
        from types import SimpleNamespace

        # Helper to convert dict to object recursively
        def dict_to_obj(d):
            if isinstance(d, dict):
                return SimpleNamespace(**{k: dict_to_obj(v) for k, v in d.items()})
            elif isinstance(d, list):
                return [dict_to_obj(item) for item in d]
            return d

        order_obj = dict_to_obj(order_data)

        # Render the row template
        html = render_template("_order_row.html", order=order_obj)
        html_parts.append(html)
        new_order_ids.append(order_data["id"])

    response = jsonify(
        {"html": "\n".join(html_parts), "new_order_ids": new_order_ids, "count": len(new_orders)}
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
