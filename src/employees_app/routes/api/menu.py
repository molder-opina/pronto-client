"""
Menu API - Endpoints para gestión de menú y productos
Handles menu items, schedules, preparation times, and recommendations
"""

import re
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required, role_required
from shared.auth.service import Roles
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import (
    MenuCategory,
    MenuItem,
    MenuItemDayPeriod,
    Order,
    OrderItem,
    ProductSchedule,
    RecommendationChangeLog,
)
from shared.serializers import error_response, success_response
from shared.services.day_period_service import DayPeriodService
from shared.services.menu_service import (
    create_menu_item,
    delete_menu_item,
    list_menu,
    update_menu_item,
)

# Create blueprint without url_prefix (inherited from parent)
menu_bp = Blueprint("menu", __name__)
logger = get_logger(__name__)


# ==================== MENU ITEMS ENDPOINTS ====================


@menu_bp.get("/menu")
def get_menu():
    """
    Obtener menú completo

    Retorna todas las categorías con sus productos disponibles.
    """
    return jsonify(success_response(list_menu()))


@menu_bp.post("/menu-items")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.CONTENT_MANAGER, Roles.CHEF])
def post_menu_item():
    """
    Crear producto de menú

    Requiere permisos: system, admin_roles, content_manager, o chef
    """
    payload = request.get_json(silent=True) or {}
    response, status = create_menu_item(payload)
    return jsonify(response), status


@menu_bp.put("/menu-items/<int:item_id>")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.CONTENT_MANAGER, Roles.CHEF])
def put_menu_item(item_id: int):
    """
    Actualizar producto de menú

    Requiere permisos: system, admin_roles, content_manager, o chef

    Body: Ver menu_service.update_menu_item para estructura completa
    """
    payload = request.get_json(silent=True) or {}
    response, status = update_menu_item(item_id, payload)
    return jsonify(response), status


@menu_bp.delete("/menu-items/<int:item_id>")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.CONTENT_MANAGER, Roles.CHEF])
def delete_menu_item_endpoint(item_id: int):
    """
    Eliminar producto de menú

    Requiere permisos: system, admin_roles, content_manager, o chef
    """
    response, status = delete_menu_item(item_id)
    return jsonify(response), status


# ==================== PRODUCT SCHEDULES ENDPOINTS ====================


@menu_bp.post("/menu-items/<int:item_id>/modifier-groups")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.CONTENT_MANAGER, Roles.CHEF])
def post_menu_item_modifier_group(item_id: int):
    """
    Asociar un grupo de modificadores a un item del menú.
    """
    payload = request.get_json(silent=True) or {}
    group_id = payload.get("modifier_group_id")
    display_order = payload.get("display_order", 0)

    if not group_id:
        return jsonify(error_response("modifier_group_id es requerido")), HTTPStatus.BAD_REQUEST

    from shared.models import MenuItemModifierGroup, ModifierGroup

    with get_session() as session:
        item = session.get(MenuItem, item_id)
        if not item:
            return jsonify(error_response("Item no encontrado")), HTTPStatus.NOT_FOUND

        group = session.get(ModifierGroup, group_id)
        if not group:
            return jsonify(error_response("Grupo no encontrado")), HTTPStatus.NOT_FOUND

        # Check existing
        existing = session.execute(
            select(MenuItemModifierGroup).where(
                MenuItemModifierGroup.menu_item_id == item_id,
                MenuItemModifierGroup.modifier_group_id == group_id,
            )
        ).scalar_one_or_none()

        if existing:
            return jsonify(error_response("La asociación ya existe")), HTTPStatus.CONFLICT

        assoc = MenuItemModifierGroup(
            menu_item_id=item_id, modifier_group_id=group_id, display_order=display_order
        )
        session.add(assoc)
        session.commit()

        return jsonify(success_response({"success": True})), HTTPStatus.CREATED


def get_item_schedules(item_id: int):
    """
    Obtener horarios de un producto

    Retorna todos los horarios configurados para un producto específico.
    """
    try:
        with get_session() as db:
            schedules = (
                db.query(ProductSchedule)
                .filter(ProductSchedule.menu_item_id == item_id)
                .order_by(ProductSchedule.day_of_week, ProductSchedule.start_time)
                .all()
            )

            day_names = {
                0: "Lunes",
                1: "Martes",
                2: "Miércoles",
                3: "Jueves",
                4: "Viernes",
                5: "Sábado",
                6: "Domingo",
                None: "Todos los días",
            }

            data = []
            for schedule in schedules:
                data.append(
                    {
                        "id": schedule.id,
                        "menu_item_id": schedule.menu_item_id,
                        "day_of_week": schedule.day_of_week,
                        "day_name": day_names.get(schedule.day_of_week, "Desconocido"),
                        "start_time": schedule.start_time,
                        "end_time": schedule.end_time,
                        "is_active": schedule.is_active,
                    }
                )

            return jsonify(success_response({"schedules": data})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching schedules: {e}")
        return jsonify(
            error_response("Error al obtener horarios")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.post("/product-schedules")
@admin_required
def create_schedule():
    """
    Crear horario de producto

    Body:
        {
            "menu_item_id": int,
            "day_of_week": int (0-6) o None para todos los días,
            "start_time": str (HH:MM),
            "end_time": str (HH:MM),
            "is_active": bool
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if "menu_item_id" not in data:
            return jsonify(error_response("menu_item_id es requerido")), HTTPStatus.BAD_REQUEST

        menu_item_id = data["menu_item_id"]
        day_of_week = data.get("day_of_week")  # Can be None for "all days"
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        is_active = data.get("is_active", True)

        # Validate day_of_week if provided
        if day_of_week is not None and not (0 <= day_of_week <= 6):
            return jsonify(
                error_response("day_of_week debe estar entre 0 (Lunes) y 6 (Domingo)")
            ), HTTPStatus.BAD_REQUEST

        # Validate time format
        if start_time and not _is_valid_time(start_time):
            return jsonify(
                error_response("start_time debe tener formato HH:MM")
            ), HTTPStatus.BAD_REQUEST

        if end_time and not _is_valid_time(end_time):
            return jsonify(
                error_response("end_time debe tener formato HH:MM")
            ), HTTPStatus.BAD_REQUEST

        with get_session() as db:
            # Verify menu item exists
            menu_item = db.query(MenuItem).filter(MenuItem.id == menu_item_id).first()
            if not menu_item:
                return jsonify(error_response("Producto no encontrado")), HTTPStatus.NOT_FOUND

            # Create schedule
            schedule = ProductSchedule(
                menu_item_id=menu_item_id,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                is_active=is_active,
            )

            db.add(schedule)
            db.commit()
            db.refresh(schedule)

            return jsonify(
                success_response(
                    {
                        "schedule": {
                            "id": schedule.id,
                            "menu_item_id": schedule.menu_item_id,
                            "day_of_week": schedule.day_of_week,
                            "start_time": schedule.start_time,
                            "end_time": schedule.end_time,
                            "is_active": schedule.is_active,
                        }
                    }
                )
            ), HTTPStatus.CREATED

    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        return jsonify(error_response("Error al crear horario")), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.put("/product-schedules/<int:schedule_id>")
@admin_required
def update_schedule(schedule_id: int):
    """
    Actualizar horario de producto

    Body: Mismos campos que crear, todos opcionales
    """
    try:
        data = request.get_json()

        with get_session() as db:
            schedule = db.query(ProductSchedule).filter(ProductSchedule.id == schedule_id).first()
            if not schedule:
                return jsonify(error_response("Horario no encontrado")), HTTPStatus.NOT_FOUND

            # Update fields if provided
            if "day_of_week" in data:
                day_of_week = data["day_of_week"]
                if day_of_week is not None and not (0 <= day_of_week <= 6):
                    return jsonify(
                        error_response("day_of_week debe estar entre 0 y 6")
                    ), HTTPStatus.BAD_REQUEST
                schedule.day_of_week = day_of_week

            if "start_time" in data:
                if data["start_time"] and not _is_valid_time(data["start_time"]):
                    return jsonify(
                        error_response("start_time debe tener formato HH:MM")
                    ), HTTPStatus.BAD_REQUEST
                schedule.start_time = data["start_time"]

            if "end_time" in data:
                if data["end_time"] and not _is_valid_time(data["end_time"]):
                    return jsonify(
                        error_response("end_time debe tener formato HH:MM")
                    ), HTTPStatus.BAD_REQUEST
                schedule.end_time = data["end_time"]

            if "is_active" in data:
                schedule.is_active = data["is_active"]

            db.commit()
            db.refresh(schedule)

            return jsonify(
                success_response(
                    {
                        "schedule": {
                            "id": schedule.id,
                            "menu_item_id": schedule.menu_item_id,
                            "day_of_week": schedule.day_of_week,
                            "start_time": schedule.start_time,
                            "end_time": schedule.end_time,
                            "is_active": schedule.is_active,
                        }
                    }
                )
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error updating schedule: {e}")
        return jsonify(
            error_response("Error al actualizar horario")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.delete("/product-schedules/<int:schedule_id>")
@admin_required
def delete_schedule(schedule_id: int):
    """
    Eliminar horario de producto
    """
    try:
        with get_session() as db:
            schedule = db.query(ProductSchedule).filter(ProductSchedule.id == schedule_id).first()
            if not schedule:
                return jsonify(error_response("Horario no encontrado")), HTTPStatus.NOT_FOUND

            db.delete(schedule)
            db.commit()

            return jsonify(
                success_response({"message": "Horario eliminado exitosamente"})
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        return jsonify(
            error_response("Error al eliminar horario")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


# ==================== PREPARATION TIME ENDPOINTS ====================


@menu_bp.patch("/menu-items/<int:item_id>/preparation-time")
@admin_required
def update_preparation_time(item_id: int):
    """
    Actualizar tiempo de preparación

    Body:
        {
            "preparation_time_minutes": int (0-300)
        }
    """
    try:
        data = request.get_json()

        if "preparation_time_minutes" not in data:
            return jsonify(
                error_response("preparation_time_minutes es requerido")
            ), HTTPStatus.BAD_REQUEST

        prep_time = data["preparation_time_minutes"]

        # Validate prep time
        if prep_time is not None:
            if not isinstance(prep_time, int) or prep_time < 0 or prep_time > 300:
                return jsonify(
                    error_response("preparation_time_minutes debe ser un entero entre 0 y 300")
                ), HTTPStatus.BAD_REQUEST

        with get_session() as db:
            menu_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if not menu_item:
                return jsonify(error_response("Producto no encontrado")), HTTPStatus.NOT_FOUND

            menu_item.preparation_time_minutes = prep_time
            db.commit()
            db.refresh(menu_item)

            return jsonify(
                success_response(
                    {
                        "item": {
                            "id": menu_item.id,
                            "name": menu_item.name,
                            "preparation_time_minutes": menu_item.preparation_time_minutes,
                        }
                    }
                )
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error updating preparation time: {e}")
        return jsonify(
            error_response("Error al actualizar tiempo de preparación")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


# ==================== RECOMMENDATIONS MANAGEMENT ENDPOINTS ====================


@menu_bp.get("/menu-items/recommendations")
@jwt_required
def get_menu_items_with_recommendations():
    """
    Obtener productos con recomendaciones

    Retorna todos los productos con sus flags de recomendación, agrupados por categoría.
    """
    try:
        with get_session() as db:
            categories = (
                db.query(MenuCategory)
                .options(
                    selectinload(MenuCategory.items)
                    .selectinload(MenuItem.day_period_assignments)
                    .selectinload(MenuItemDayPeriod.period)
                )
                .order_by(MenuCategory.display_order)
                .all()
            )

            result = []
            for category in categories:
                items = []
                for item in category.items:
                    items.append(
                        {
                            "id": item.id,
                            "name": item.name,
                            "description": item.description,
                            "price": float(item.price),
                            "is_available": item.is_available,
                            "image_path": item.image_path,
                            "is_breakfast_recommended": item.is_breakfast_recommended,
                            "is_afternoon_recommended": item.is_afternoon_recommended,
                            "is_night_recommended": item.is_night_recommended,
                            "recommendation_periods": [
                                assignment.period.period_key
                                for assignment in item.day_period_assignments
                                if assignment.tag_type == "recommendation" and assignment.period
                            ],
                        }
                    )

                result.append({"id": category.id, "name": category.name, "items": items})

            return jsonify(success_response({"categories": result})), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching menu items with recommendations: {e}")
        return jsonify(
            error_response("Error al obtener productos")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.patch("/menu-items/<int:item_id>/recommendations")
@role_required([Roles.SUPER_ADMIN, Roles.ADMIN_ROLES, Roles.WAITER, Roles.CONTENT_MANAGER])
def update_item_recommendations(item_id: int):
    """
    Actualizar recomendaciones de producto

    Body:
        {
            "is_breakfast_recommended": bool (opcional),
            "is_afternoon_recommended": bool (opcional),
            "is_night_recommended": bool (opcional)
        }
    """
    try:
        data = request.get_json()

        with get_session() as db:
            menu_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if not menu_item:
                return jsonify(error_response("Producto no encontrado")), HTTPStatus.NOT_FOUND

            existing_keys = {
                assignment.period.period_key
                for assignment in menu_item.day_period_assignments
                if assignment.tag_type == "recommendation" and assignment.period
            }

            target_keys = None

            if isinstance(data.get("recommendation_periods"), list):
                target_keys = [str(key) for key in data["recommendation_periods"] if key]
            elif "period_key" in data:
                period_key = data.get("period_key")
                if not period_key:
                    return jsonify(
                        error_response("period_key es requerido")
                    ), HTTPStatus.BAD_REQUEST
                target_keys = list(existing_keys)
                if data.get("enabled", True):
                    if period_key not in target_keys:
                        target_keys.append(period_key)
                else:
                    target_keys = [key for key in target_keys if key != period_key]
            else:
                valid_fields = [
                    "is_breakfast_recommended",
                    "is_afternoon_recommended",
                    "is_night_recommended",
                ]
                if not any(field in data for field in valid_fields):
                    return jsonify(
                        error_response("Al menos un campo de recomendación es requerido")
                    ), HTTPStatus.BAD_REQUEST
                target_keys = []
                if data.get("is_breakfast_recommended"):
                    target_keys.append("breakfast")
                if data.get("is_afternoon_recommended"):
                    target_keys.append("afternoon")
                if data.get("is_night_recommended"):
                    target_keys.append("night")

            DayPeriodService.update_item_periods(db, menu_item, target_keys)

            # Log the change
            employee_id = get_employee_id()
            if "period_key" in data:
                period_key = data["period_key"]
                action = "added" if data.get("enabled", True) else "removed"
                change_log = RecommendationChangeLog(
                    menu_item_id=item_id,
                    period_key=period_key,
                    action=action,
                    employee_id=employee_id,
                )
                db.add(change_log)

            db.commit()
            db.refresh(menu_item)

            return jsonify(
                success_response(
                    {
                        "item": {
                            "id": menu_item.id,
                            "name": menu_item.name,
                            "recommendation_periods": [
                                assignment.period.period_key
                                for assignment in menu_item.day_period_assignments
                                if assignment.tag_type == "recommendation" and assignment.period
                            ],
                            "is_breakfast_recommended": menu_item.is_breakfast_recommended,
                            "is_afternoon_recommended": menu_item.is_afternoon_recommended,
                            "is_night_recommended": menu_item.is_night_recommended,
                        }
                    }
                )
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error updating recommendations: {e}")
        return jsonify(
            error_response("Error al actualizar recomendaciones")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.get("/menu-items/popular")
@jwt_required
def get_popular_menu_items():
    """
    Obtener productos más populares basados en órdenes

    Retorna los productos más vendidos en los últimos 30 días.
    Query params:
        - days: número de días a considerar (default: 30)
        - limit: número de productos a retornar (default: 10)
    """
    try:
        days = int(request.args.get("days", 30))
        limit = int(request.args.get("limit", 10))

        with get_session() as db:
            from datetime import datetime, timedelta

            cutoff_date = datetime.now() - timedelta(days=days)

            # Get most ordered items
            popular_items = (
                db.query(
                    MenuItem.id,
                    MenuItem.name,
                    MenuItem.description,
                    MenuItem.price,
                    MenuItem.category_id,
                    MenuCategory.name.label("category_name"),
                    func.count(OrderItem.id).label("order_count"),
                    func.sum(OrderItem.quantity).label("total_quantity"),
                )
                .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
                .join(Order, Order.id == OrderItem.order_id)
                .join(MenuCategory, MenuCategory.id == MenuItem.category_id)
                .filter(Order.created_at >= cutoff_date)
                .filter(Order.payment_status == "paid")
                .group_by(
                    MenuItem.id,
                    MenuItem.name,
                    MenuItem.description,
                    MenuItem.price,
                    MenuItem.category_id,
                    MenuCategory.name,
                )
                .order_by(desc("total_quantity"))
                .limit(limit)
                .all()
            )

            data = []
            for item in popular_items:
                data.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "price": float(item.price),
                        "category_id": item.category_id,
                        "category_name": item.category_name,
                        "order_count": item.order_count,
                        "total_quantity": item.total_quantity,
                    }
                )

            return jsonify(success_response({"popular_items": data, "days": days})), HTTPStatus.OK

    except ValueError:
        return jsonify(error_response("Parámetros inválidos")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error fetching popular items: {e}")
        return jsonify(
            error_response("Error al obtener productos populares")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@menu_bp.get("/menu-items/<int:item_id>/recommendation-history")
@jwt_required
def get_recommendation_history(item_id: int):
    """
    Obtener historial de cambios de recomendaciones para un producto

    Retorna el historial de cuándo se agregó/quitó de recomendaciones.
    """
    try:
        with get_session() as db:
            # Verify menu item exists
            menu_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if not menu_item:
                return jsonify(error_response("Producto no encontrado")), HTTPStatus.NOT_FOUND

            # Get change history
            history = (
                db.query(RecommendationChangeLog)
                .filter(RecommendationChangeLog.menu_item_id == item_id)
                .order_by(RecommendationChangeLog.created_at.desc())
                .limit(50)
                .all()
            )

            data = []
            for change in history:
                employee_name = change.employee.name if change.employee else "Sistema"
                data.append(
                    {
                        "id": change.id,
                        "period_key": change.period_key,
                        "action": change.action,
                        "employee_name": employee_name,
                        "created_at": change.created_at.isoformat() if change.created_at else None,
                    }
                )

            return jsonify(
                success_response({"item_id": item_id, "item_name": menu_item.name, "history": data})
            ), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching recommendation history: {e}")
        return jsonify(
            error_response("Error al obtener historial")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


# ==================== HELPER FUNCTIONS ====================


def _is_valid_time(time_str: str) -> bool:
    """
    Validate time string format HH:MM
    """
    if not time_str or not isinstance(time_str, str):
        return False
    pattern = r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$"
    return bool(re.match(pattern, time_str))
