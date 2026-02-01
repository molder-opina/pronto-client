"""
Customers API - Endpoints para gestión de clientes
Handles customer information updates
"""

from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from employees_app.decorators import role_required
from shared.constants import Roles
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Customer, Order, OrderItem
from shared.serializers import error_response, serialize_customer, success_response

# Create blueprint without url_prefix (inherited from parent)
customers_bp = Blueprint("customers", __name__)
logger = get_logger(__name__)


@customers_bp.patch("/customers/<int:customer_id>/physical-description")
@role_required([Roles.SUPER_ADMIN, Roles.WAITER])
def update_customer_physical_description(customer_id: int):
    """
    Actualizar descripción física del cliente

    Permite a meseros y admins agregar una descripción física del cliente
    para ayudar en su identificación.

    Body:
        {
            "physical_description": str (máx 500 caracteres)
        }

    Requiere rol de mesero o administrador.
    """
    try:
        data = request.get_json() or {}
        description = data.get("physical_description", "").strip()

        # Limit description length
        if len(description) > 500:
            return jsonify(
                error_response("Descripción demasiado larga (máximo 500 caracteres)")
            ), HTTPStatus.BAD_REQUEST

        with get_session() as db:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                return jsonify(error_response("Cliente no encontrado")), HTTPStatus.NOT_FOUND

            customer.physical_description = description if description else None
            db.commit()
            db.refresh(customer)

            return jsonify(
                success_response({"customer": serialize_customer(customer, mask_anonymous=False)})
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error updating customer description: {e}")
        return jsonify(
            error_response("Error al actualizar descripción")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@customers_bp.get("/customers/stats")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER])
def get_customer_stats():
    """
    Obtener métricas básicas de clientes.
    """
    try:
        with get_session() as db:
            total = db.scalar(select(func.count()).select_from(Customer)) or 0
            cutoff = datetime.utcnow() - timedelta(days=30)
            active = (
                db.scalar(
                    select(func.count(func.distinct(Order.customer_id))).where(
                        Order.created_at >= cutoff
                    )
                )
                or 0
            )

        return jsonify(success_response({"total": total, "active": active})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error loading customer stats: {e}", exc_info=True)
        return jsonify(
            error_response("Error al cargar estadísticas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@customers_bp.get("/customers/search")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER])
def search_customers():
    """
    Buscar clientes por nombre, email, teléfono o ID.
    """
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(success_response({"customers": []})), HTTPStatus.OK

    query_lower = query.lower()
    cutoff = datetime.utcnow() - timedelta(days=30)

    try:
        with get_session() as db:
            customers = db.query(Customer).order_by(Customer.created_at.desc()).all()

            order_stats = db.execute(
                select(
                    Order.customer_id,
                    func.count(Order.id),
                    func.max(Order.created_at),
                ).group_by(Order.customer_id)
            ).all()
            stats_map = {
                row[0]: {"total_orders": row[1] or 0, "last_order_at": row[2]}
                for row in order_stats
            }

            matches = []
            for customer in customers:
                name = (customer.name or "").lower()
                email = (customer.email or "").lower()
                phone = (customer.phone or "").lower()
                if (
                    query_lower in str(customer.id).lower()
                    or query_lower in name
                    or query_lower in email
                    or query_lower in phone
                ):
                    stats = stats_map.get(customer.id, {})
                    last_order_at = stats.get("last_order_at")
                    payload = serialize_customer(customer, mask_anonymous=False) or {}
                    payload.update(
                        {
                            "total_orders": stats.get("total_orders", 0),
                            "is_active": bool(last_order_at and last_order_at >= cutoff),
                            "created_at": customer.created_at.isoformat()
                            if customer.created_at
                            else None,
                        }
                    )
                    matches.append(payload)

        return jsonify(success_response({"customers": matches})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error searching customers: {e}", exc_info=True)
        return jsonify(error_response("Error al buscar clientes")), HTTPStatus.INTERNAL_SERVER_ERROR


@customers_bp.get("/customers/<int:customer_id>")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER])
def get_customer_detail(customer_id: int):
    """
    Obtener información detallada de un cliente.
    """
    cutoff = datetime.utcnow() - timedelta(days=30)
    try:
        with get_session() as db:
            customer = db.get(Customer, customer_id)
            if not customer:
                return jsonify(error_response("Cliente no encontrado")), HTTPStatus.NOT_FOUND

            orders = db.query(Order).filter(Order.customer_id == customer_id).all()
            total_spent = sum(float(order.total_amount or 0) for order in orders)
            last_order_at = max(
                (order.created_at for order in orders if order.created_at), default=None
            )

            payload = serialize_customer(customer, mask_anonymous=False) or {}
            payload.update(
                {
                    "total_orders": len(orders),
                    "total_spent": total_spent,
                    "is_active": bool(last_order_at and last_order_at >= cutoff),
                    "created_at": customer.created_at.isoformat() if customer.created_at else None,
                }
            )

        return jsonify(success_response({"customer": payload})), HTTPStatus.OK
    except Exception as e:
        logger.error(f"Error loading customer detail: {e}", exc_info=True)
        return jsonify(error_response("Error al cargar cliente")), HTTPStatus.INTERNAL_SERVER_ERROR


@customers_bp.get("/customers/<int:customer_id>/coupons")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER])
def get_customer_coupons(customer_id: int):
    """
    Placeholder para cupones del cliente.
    """
    return jsonify(success_response({"coupons": []})), HTTPStatus.OK


@customers_bp.get("/customers/<int:customer_id>/orders")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN, Roles.WAITER, Roles.CASHIER])
def list_customer_orders(customer_id: int):
    """
    Obtener historial de órdenes para un cliente en particular.
    Devuelve la lista completa (ordenada por fecha descendente) para que el panel
    pueda paginarla en el front.
    """
    try:
        with get_session() as db:
            orders = (
                db.query(Order)
                .options(
                    joinedload(Order.items).joinedload(OrderItem.menu_item),
                    joinedload(Order.session),
                )
                .filter(Order.customer_id == customer_id)
                .order_by(Order.created_at.desc())
                .all()
            )

            payload = []
            for order in orders:
                payload.append(
                    {
                        "id": order.id,
                        "created_at": order.created_at.isoformat() if order.created_at else None,
                        "status": order.workflow_status,
                        "total": float(order.total_amount),
                        "subtotal": float(order.subtotal),
                        "items": [
                            {
                                "id": item.id,
                                "name": item.menu_item.name if item.menu_item else item.custom_name,
                                "quantity": item.quantity,
                                "price": float(item.unit_price),
                            }
                            for item in order.items
                        ],
                        "session": {
                            "id": order.session_id,
                            "table_number": order.session.table_number if order.session else None,
                        },
                    }
                )

            return jsonify({"status": "success", "data": {"orders": payload}})
    except Exception as exc:
        logger.error("Error retrieving customer orders %s: %s", customer_id, exc)
        return jsonify(
            {"status": "error", "message": "Error al cargar órdenes"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
