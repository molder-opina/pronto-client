"""
Debug API - Endpoints para testing y desarrollo
Solo disponible cuando DEBUG_MODE está habilitado
"""

from datetime import datetime
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

from shared.extensions import csrf
from shared.jwt_middleware import get_current_user, jwt_required
from shared.constants import OrderStatus as WorkflowStatus
from shared.constants import SessionStatus
from shared.db import get_session as get_db_session
from shared.models import (
    Area,
    Customer,
    MenuItem,
    Order,
    OrderItem,
    Table,
)
from shared.models import (
    DiningSession as OrderSession,
)
from shared.config import read_bool

# Create blueprint without url_prefix (inherited from parent)
debug_bp = Blueprint("debug", __name__, url_prefix="/debug")


def is_debug_enabled():
    """Check if debug mode is enabled"""
    return read_bool("DEBUG_MODE", "false")


@debug_bp.before_request
def check_debug_mode():
    """Middleware to check if debug mode is enabled before processing requests"""
    # Permitir system en entorno productivo para pruebas controladas
    user = get_current_user()
    employee_role = user.get("role") if user else None
    if not is_debug_enabled() and employee_role != "system":
        return jsonify(
            {
                "error": "Debug endpoints are disabled",
                "message": "Enable DEBUG_MODE in configuration to use debug endpoints",
            }
        ), HTTPStatus.FORBIDDEN


@debug_bp.post("/orders")
@csrf.exempt
def create_test_order():
    """
    Crear una orden de prueba para testing

    Body:
        {
            "customer": {
                "name": "Cliente Debug",
                "email": "debug@test.com",
                "phone": "+52 55 9999 9999"
            },
            "table_number": "Mesa Debug",
            "items": [
                {"menu_item_id": 1, "quantity": 2},
                {"menu_item_id": 2, "quantity": 1}
            ]
        }

    Returns:
        {
            "order_id": int,
            "session_id": int,
            "message": str
        }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), HTTPStatus.BAD_REQUEST

        with get_db_session() as db:
            # Obtener o crear cliente
            customer_data = data.get("customer", {})
            customer_email = customer_data.get(
                "email", f"debug_{datetime.now().timestamp()}@test.com"
            )

            customer = db.query(Customer).filter_by(email=customer_email).first()

            if not customer:
                customer = Customer(
                    name=customer_data.get("name", "Cliente Debug"),
                    email=customer_email,
                    phone=customer_data.get("phone", "+52 55 9999 9999"),
                )
                db.add(customer)
                db.flush()

            # Crear sesión
            table_number = data.get("table_number", f"Debug-{int(datetime.now().timestamp())}")
            order_session = OrderSession(
                customer_id=customer.id,
                table_number=table_number,
                status=SessionStatus.OPEN.value,
                opened_at=datetime.utcnow(),
            )
            db.add(order_session)
            db.flush()

            # Obtener items del menú
            items_data = data.get("items", [])
            if not items_data:
                # Si no hay items, usar los primeros 2 del menú
                menu_items = db.query(MenuItem).filter_by(is_available=True).limit(2).all()
                if not menu_items:
                    return jsonify(
                        {"error": "No hay productos disponibles para crear la orden de prueba"}
                    ), HTTPStatus.BAD_REQUEST
                items_data = [{"menu_item_id": item.id, "quantity": 1} for item in menu_items]

            # Calcular total
            total_amount = 0
            order_items = []

            for item_data in items_data:
                menu_item_id = item_data.get("menu_item_id")
                quantity = item_data.get("quantity", 1)

                menu_item = db.query(MenuItem).filter_by(id=menu_item_id).first()
                if not menu_item:
                    continue

                item_total = menu_item.price * quantity
                total_amount += item_total

                order_items.append(
                    {
                        "menu_item_id": menu_item_id,
                        "name": menu_item.name,
                        "quantity": quantity,
                        "unit_price": float(menu_item.price),
                    }
                )

            # Crear orden
            order = Order(
                session_id=order_session.id,
                customer_id=customer.id,
                total_amount=total_amount,
                workflow_status=WorkflowStatus.NEW.value,
                created_at=datetime.utcnow(),
            )
            db.add(order)
            db.flush()

            # Crear OrderItems
            for item_data in items_data:
                menu_item_id = item_data.get("menu_item_id")
                quantity = item_data.get("quantity", 1)

                menu_item = db.query(MenuItem).filter_by(id=menu_item_id).first()
                if not menu_item:
                    continue

                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item_id,
                    quantity=quantity,
                    unit_price=menu_item.price,
                    name=menu_item.name,
                )
                db.add(order_item)

            db.commit()

            return jsonify(
                {
                    "order_id": order.id,
                    "session_id": order_session.id,
                    "customer_id": customer.id,
                    "total_amount": float(total_amount),
                    "table_number": table_number,
                    "message": "Orden de prueba creada exitosamente",
                }
            ), HTTPStatus.CREATED

    except Exception as e:
        current_app.logger.error(f"Error creating test order: {e!s}")
        return jsonify(
            {"error": "Failed to create test order", "message": str(e)}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@debug_bp.delete("/orders/<int:order_id>")
def delete_test_order(order_id: int):
    """
    Eliminar una orden de prueba

    Returns:
        {"message": "Order deleted successfully"}
    """
    try:
        db = get_db_session()

        order = db.query(Order).filter_by(id=order_id).first()
        if not order:
            return jsonify({"error": "Order not found"}), HTTPStatus.NOT_FOUND

        # Eliminar OrderItems asociados
        db.query(OrderItem).filter_by(order_id=order_id).delete()

        # Eliminar la orden
        db.delete(order)
        db.commit()

        return jsonify({"message": "Order deleted successfully"}), HTTPStatus.OK

    except Exception as e:
        db.rollback()
        current_app.logger.error(f"Error deleting test order: {e!s}")
        return jsonify(
            {"error": "Failed to delete test order", "message": str(e)}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@debug_bp.get("/status")
def debug_status():
    """
    Verificar el estado del modo debug

    Returns:
        {
            "debug_enabled": bool,
            "endpoints_available": list
        }
    """
    return jsonify(
        {
            "debug_enabled": is_debug_enabled(),
            "endpoints_available": [
                "POST /api/debug/orders - Create test order",
                "DELETE /api/debug/orders/<id> - Delete test order",
                "DELETE /api/debug/cleanup - Clear ALL orders and sessions",
                "GET /api/debug/status - Check debug status",
            ],
        }
    ), HTTPStatus.OK


@debug_bp.get("/tables")
def list_tables():
    """Listar mesas activas para depuración."""
    with get_db_session() as db:
        tables = (
            db.query(Table, Area)
            .join(Area, Table.area_id == Area.id)
            .filter(Table.is_active == True)  # noqa: E712
            .order_by(Area.prefix, Area.name, Table.table_number)
            .all()
        )
        return jsonify(
            {
                "tables": [
                    {
                        "id": t.id,
                        "table_number": t.table_number,
                        "area": {
                            "id": a.id,
                            "prefix": a.prefix,
                            "name": a.name,
                        },
                        "capacity": t.capacity,
                        "status": t.status,
                    }
                    for t, a in tables
                ]
            }
        )


@debug_bp.post("/sessions/<int:session_id>/change-table")
def change_session_table(session_id: int):
    """Actualizar la mesa de una sesión (solo para debug)."""
    payload = request.get_json(silent=True) or {}
    table_number = (payload.get("table_number") or "").strip()
    if not table_number:
        return jsonify({"error": "table_number es requerido"}), HTTPStatus.BAD_REQUEST

    with get_db_session() as db:
        session_obj = db.query(OrderSession).get(session_id)
        if not session_obj:
            return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

        table = (
            db.query(Table)
            .filter(Table.is_active == True)  # noqa: E712
            .filter(Table.table_number == table_number)
            .first()
        )
        if not table:
            return jsonify({"error": "Mesa no encontrada o inactiva"}), HTTPStatus.NOT_FOUND

        session_obj.table_number = table.table_number
        db.add(session_obj)
        db.commit()
        db.refresh(session_obj)

        return jsonify(
            {
                "session_id": session_obj.id,
                "table_number": session_obj.table_number,
                "area_id": table.area_id,
                "status": session_obj.status,
            }
        )


@debug_bp.delete("/cleanup")
def cleanup_all_orders():
    """
    DANGER: Elimina TODAS las órdenes, sesiones y datos relacionados.
    Solo usar para limpiar datos de prueba.

    Query params:
        confirm=yes (required) - Confirmación de seguridad

    Returns:
        {
            "message": str,
            "deleted": {
                "order_items": int,
                "order_item_modifiers": int,
                "orders": int,
                "sessions": int,
                "waiter_calls": int,
                "notifications": int,
                "split_bills": int
            }
        }
    """
    from shared.models import (
        Feedback,
        Notification,
        OrderItemModifier,
        OrderModification,
        OrderStatusHistory,
        SplitBill,
        SplitBillAssignment,
        SplitBillPerson,
        WaiterCall,
    )

    # Safety check
    confirm = request.args.get("confirm", "").lower()
    if confirm != "yes":
        return jsonify(
            {
                "error": "Safety check failed",
                "message": "Add ?confirm=yes to confirm deletion of ALL orders and sessions",
            }
        ), HTTPStatus.BAD_REQUEST

    try:
        with get_db_session() as db:
            # Count before deletion
            counts = {
                "order_status_history": db.query(OrderStatusHistory).count(),
                "order_modifications": db.query(OrderModification).count(),
                "order_item_modifiers": db.query(OrderItemModifier).count(),
                "order_items": db.query(OrderItem).count(),
                "orders": db.query(Order).count(),
                "sessions": db.query(OrderSession).count(),
                "waiter_calls": db.query(WaiterCall).count(),
                "notifications": db.query(Notification).count(),
                "split_bill_assignments": db.query(SplitBillAssignment).count(),
                "split_bill_people": db.query(SplitBillPerson).count(),
                "split_bills": db.query(SplitBill).count(),
                "feedback": db.query(Feedback).count(),
            }

            # Delete in correct order (foreign key dependencies)
            db.query(SplitBillAssignment).delete()
            db.query(SplitBillPerson).delete()
            db.query(SplitBill).delete()
            db.query(Feedback).delete()
            db.query(OrderStatusHistory).delete()
            db.query(OrderModification).delete()
            db.query(OrderItemModifier).delete()
            db.query(OrderItem).delete()
            db.query(Notification).delete()
            db.query(WaiterCall).delete()
            db.query(Order).delete()
            db.query(OrderSession).delete()

            db.commit()

            total_deleted = sum(counts.values())

            return jsonify(
                {
                    "message": f"Cleanup completed. {total_deleted} records deleted.",
                    "deleted": counts,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error during cleanup: {e!s}")
        return jsonify(
            {"error": "Cleanup failed", "message": str(e)}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
