"""
Reports API - Reportes y análisis de datos

Este módulo proporciona endpoints para generar reportes de ventas,
productos más vendidos, horarios pico y propinas de meseros.
"""

from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import Date, and_, cast, func

from employees_app.decorators import login_required
from shared.constants import PaymentStatus
from shared.db import get_session
from shared.jwt_middleware import jwt_required
from shared.logging_config import get_logger
from shared.models import Area, Employee, MenuItem, Order, OrderItem, Table
from shared.serializers import error_response, success_response

reports_bp = Blueprint("reports", __name__)
logger = get_logger(__name__)


def to_local_date(col):
    """Convierte columna UTC a fecha local (Mexico City)"""
    return cast(func.timezone("America/Mexico_City", func.timezone("UTC", col)), Date)


@reports_bp.get("/reports/sales")
@jwt_required
def get_sales_report():
    """
    Obtiene reporte de ventas con filtrado por rango de fechas y agrupación.

    Query params:
    - start_date: YYYY-MM-DD (default: 7 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    - group_by: day|week|month (default: day)
    """
    try:
        # Parse query parameters
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")
        group_by = request.args.get("group_by", "day")

        # Default to last 7 days
        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=7))
        )

        with get_session() as db:
            # Build query based on grouping
            if group_by == "day":
                # Convert UTC created_at to local date for grouping and filtering
                date_col = to_local_date(Order.created_at)
                query = (
                    db.query(
                        date_col.label("date"),
                        func.count(Order.id).label("order_count"),
                        func.sum(Order.total_amount).label("total_sales"),
                        func.sum(Order.tip_amount).label("total_tips"),
                        func.avg(Order.total_amount).label("avg_order_value"),
                    )
                    .filter(
                        and_(
                            to_local_date(Order.created_at) >= start_date,
                            to_local_date(Order.created_at) <= end_date,
                            Order.payment_status == PaymentStatus.PAID.value,
                        )
                    )
                    .group_by(date_col)
                    .order_by(date_col)
                )

            elif group_by == "week":
                # Group by ISO week (PostgreSQL uses to_char instead of date_format)
                week_col = func.to_char(to_local_date(Order.created_at), "IYYY-IW")
                query = (
                    db.query(
                        week_col.label("date"),
                        func.count(Order.id).label("order_count"),
                        func.sum(Order.total_amount).label("total_sales"),
                        func.sum(Order.tip_amount).label("total_tips"),
                        func.avg(Order.total_amount).label("avg_order_value"),
                    )
                    .filter(
                        and_(
                            to_local_date(Order.created_at) >= start_date,
                            to_local_date(Order.created_at) <= end_date,
                            Order.payment_status == PaymentStatus.PAID.value,
                        )
                    )
                    .group_by(week_col)
                    .order_by(week_col)
                )

            elif group_by == "month":
                # PostgreSQL uses to_char instead of date_format
                month_col = func.to_char(to_local_date(Order.created_at), "YYYY-MM")
                query = (
                    db.query(
                        month_col.label("date"),
                        func.count(Order.id).label("order_count"),
                        func.sum(Order.total_amount).label("total_sales"),
                        func.sum(Order.tip_amount).label("total_tips"),
                        func.avg(Order.total_amount).label("avg_order_value"),
                    )
                    .filter(
                        and_(
                            to_local_date(Order.created_at) >= start_date,
                            to_local_date(Order.created_at) <= end_date,
                            Order.payment_status == PaymentStatus.PAID.value,
                        )
                    )
                    .group_by(month_col)
                    .order_by(month_col)
                )

            else:
                return jsonify(error_response("Invalid group_by parameter")), HTTPStatus.BAD_REQUEST

            results = query.all()

            # Format results
            data = []
            for row in results:
                data.append(
                    {
                        "date": str(row.date),
                        "order_count": row.order_count,
                        "total_sales": float(row.total_sales or 0),
                        "total_tips": float(row.total_tips or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                    }
                )

            # Calculate totals
            total_orders = sum(d["order_count"] for d in data)
            total_revenue = sum(d["total_sales"] for d in data)
            total_tips_sum = sum(d["total_tips"] for d in data)

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "summary": {
                            "total_orders": total_orders,
                            "total_revenue": total_revenue,
                            "total_tips": total_tips_sum,
                            "avg_order_value": total_revenue / total_orders
                            if total_orders > 0
                            else 0,
                        },
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "group_by": group_by,
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating sales report: {e}")
        return jsonify(
            error_response("Error al generar reporte de ventas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/top-products")
@jwt_required
def get_top_products():
    """
    Obtiene reporte de productos más vendidos.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    - limit: int (default: 10)
    """
    try:
        # Parse query parameters
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")
        limit = int(request.args.get("limit", 10))

        # Default to last 30 days
        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=30))
        )

        with get_session() as db:
            query = (
                db.query(
                    MenuItem.id,
                    MenuItem.name,
                    func.sum(OrderItem.quantity).label("total_quantity"),
                    func.count(OrderItem.id).label("order_count"),
                    func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
                )
                .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
                .join(Order, Order.id == OrderItem.order_id)
                .filter(
                    and_(
                        to_local_date(Order.created_at) >= start_date,
                        to_local_date(Order.created_at) <= end_date,
                        Order.payment_status == PaymentStatus.PAID.value,
                    )
                )
                .group_by(MenuItem.id, MenuItem.name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(limit)
            )

            results = query.all()

            data = []
            for row in results:
                data.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "total_quantity": row.total_quantity,
                        "order_count": row.order_count,
                        "total_revenue": float(row.total_revenue or 0),
                    }
                )

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "limit": limit,
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid parameter: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating top products report: {e}")
        return jsonify(
            error_response("Error al generar reporte de productos")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/peak-hours")
@jwt_required
def get_peak_hours():
    """
    Obtiene análisis de horarios pico mostrando volumen de órdenes por hora del día.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    """
    try:
        # Parse query parameters
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")

        # Default to last 30 days
        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=30))
        )

        with get_session() as db:
            # Group by hour of day (PostgreSQL uses to_char instead of date_format)
            hour_col = func.to_char(Order.created_at, "HH24")
            query = (
                db.query(
                    hour_col.label("hour"),
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                )
                .filter(
                    and_(
                        to_local_date(Order.created_at) >= start_date,
                        to_local_date(Order.created_at) <= end_date,
                    )
                )
                .group_by(hour_col)
                .order_by(hour_col)
            )

            results = query.all()

            # Format results with hour labels
            data = []
            for row in results:
                hour = int(row.hour)
                data.append(
                    {
                        "hour": hour,
                        "hour_label": f"{hour:02d}:00",
                        "order_count": row.order_count,
                        "total_sales": float(row.total_sales or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                    }
                )

            # Find peak hour
            peak_hour = max(data, key=lambda x: x["order_count"]) if data else None

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "peak_hour": peak_hour,
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating peak hours report: {e}")
        return jsonify(
            error_response("Error al generar reporte de horarios")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/waiter-tips")
@jwt_required
def get_waiter_tips_report():
    """
    Obtiene reporte de propinas por mesero.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    """
    try:
        # Parse query parameters
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")

        # Default to last 30 days
        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=30))
        )

        with get_session() as db:
            query = (
                db.query(
                    Employee.id,
                    Employee.name_encrypted,
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.tip_amount).label("total_tips"),
                    func.avg(Order.tip_amount).label("avg_tip"),
                    func.sum(Order.total_amount).label("total_sales"),
                )
                .join(Order, Order.waiter_id == Employee.id)
                .filter(
                    and_(
                        to_local_date(Order.created_at) >= start_date,
                        to_local_date(Order.created_at) <= end_date,
                        Order.payment_status == PaymentStatus.PAID.value,
                        Order.tip_amount > 0,
                    )
                )
                .group_by(Employee.id, Employee.name_encrypted)
                .order_by(func.sum(Order.tip_amount).desc())
            )

            results = query.all()

            data = []
            for row in results:
                # Decrypt employee name
                from shared.security import decrypt_string

                waiter_name = decrypt_string(row.name_encrypted) or f"Employee #{row.id}"

                data.append(
                    {
                        "waiter_id": row.id,
                        "waiter_name": waiter_name,
                        "order_count": row.order_count,
                        "total_tips": float(row.total_tips or 0),
                        "avg_tip": float(row.avg_tip or 0),
                        "total_sales": float(row.total_sales or 0),
                        "tip_percentage": (float(row.total_tips or 0) / float(row.total_sales or 1))
                        * 100,
                    }
                )

            total_tips = sum(d["total_tips"] for d in data)

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "summary": {"total_tips": total_tips, "waiter_count": len(data)},
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating waiter tips report: {e}")
        return jsonify(
            error_response("Error al generar reporte de propinas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/areas/performance")
@jwt_required
def get_areas_performance():
    """
    Obtiene reporte de rendimiento por área del restaurante.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    """
    try:
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")

        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=30))
        )

        with get_session() as db:
            query = (
                db.query(
                    Area.id,
                    Area.name,
                    Area.color,
                    Area.prefix,
                    func.count(Table.id).label("table_count"),
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                    func.sum(Order.tip_amount).label("total_tips"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.coalesce(
                        func.sum(Order.total_amount) / func.count(Order.id),
                        0,
                    ).label("revenue_per_order"),
                )
                .outerjoin(Table, Table.area_id == Area.id)
                .outerjoin(Order, Order.table_id == Table.id)
                .filter(
                    and_(
                        to_local_date(Order.created_at) >= start_date,
                        to_local_date(Order.created_at) <= end_date,
                        Area.is_active == True,
                    )
                )
                .group_by(Area.id, Area.name, Area.color, Area.prefix)
                .order_by(func.sum(Order.total_amount).desc())
            )

            results = query.all()

            data = []
            for row in results:
                data.append(
                    {
                        "area_id": row.id,
                        "area_name": row.name,
                        "area_color": row.color,
                        "area_prefix": row.prefix,
                        "table_count": row.table_count,
                        "order_count": row.order_count,
                        "total_sales": float(row.total_sales or 0),
                        "total_tips": float(row.total_tips or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                        "revenue_per_order": float(row.revenue_per_order or 0),
                    }
                )

            total_sales = sum(d["total_sales"] for d in data)
            total_orders = sum(d["order_count"] for d in data)

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "summary": {
                            "total_sales": total_sales,
                            "total_orders": total_orders,
                            "area_count": len(data),
                        },
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating areas performance report: {e}")
        return jsonify(
            error_response("Error al generar reporte de rendimiento por área")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/areas/occupancy")
@jwt_required
def get_areas_occupancy():
    """
    Obtiene reporte de ocupación por área del restaurante.

    Query params:
    - start_date: YYYY-MM-DD (default: 7 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    """
    try:
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")

        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=7))
        )

        with get_session() as db:
            query = (
                db.query(
                    Area.id,
                    Area.name,
                    Area.color,
                    Area.prefix,
                    func.count(Table.id).label("total_tables"),
                    func.count(
                        func.distinct(
                            func.case((to_local_date(Order.created_at) >= start_date, Table.id))
                        )
                    ).label("tables_used"),
                )
                .join(Table, Table.area_id == Area.id)
                .filter(Area.is_active == True)
                .group_by(Area.id, Area.name, Area.color, Area.prefix)
                .order_by(Area.name)
            )

            results = query.all()

            data = []
            for row in results:
                occupancy_rate = (
                    (row.tables_used / row.total_tables) * 100 if row.total_tables > 0 else 0
                )

                data.append(
                    {
                        "area_id": row.id,
                        "area_name": row.name,
                        "area_color": row.color,
                        "area_prefix": row.prefix,
                        "total_tables": row.total_tables,
                        "tables_used": row.tables_used,
                        "tables_available": row.total_tables - row.tables_used,
                        "occupancy_rate": round(occupancy_rate, 2),
                    }
                )

            total_tables = sum(d["total_tables"] for d in data)
            total_tables_used = sum(d["tables_used"] for d in data)
            avg_occupancy = (total_tables_used / total_tables) * 100 if total_tables > 0 else 0

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "summary": {
                            "total_tables": total_tables,
                            "total_tables_used": total_tables_used,
                            "avg_occupancy_rate": round(avg_occupancy, 2),
                        },
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating areas occupancy report: {e}")
        return jsonify(
            error_response("Error al generar reporte de ocupación por área")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@reports_bp.get("/reports/areas/trends")
@jwt_required
def get_areas_trends():
    """
    Obtiene tendencias de ventas por área en el tiempo.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    - group_by: day|week|month (default: day)
    """
    try:
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")
        group_by = request.args.get("group_by", "day")

        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else datetime.utcnow().date()
        )
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else (end_date - timedelta(days=30))
        )

        with get_session() as db:
            if group_by == "day":
                date_col = to_local_date(Order.created_at)
                grouping_col = date_col
            elif group_by == "week":
                date_col = to_local_date(Order.created_at)
                grouping_col = func.to_char(date_col, "IYYY-IW")
            else:
                date_col = to_local_date(Order.created_at)
                grouping_col = func.to_char(date_col, "YYYY-MM")

            query = (
                db.query(
                    grouping_col.label("period"),
                    Area.id.label("area_id"),
                    Area.name.label("area_name"),
                    Area.color.label("area_color"),
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                )
                .join(Table, Table.id == Order.table_id)
                .join(Area, Area.id == Table.area_id)
                .filter(
                    and_(
                        to_local_date(Order.created_at) >= start_date,
                        to_local_date(Order.created_at) <= end_date,
                        Area.is_active == True,
                        Order.payment_status == PaymentStatus.PAID.value,
                    )
                )
                .group_by(grouping_col, Area.id, Area.name, Area.color)
                .order_by(grouping_col, Area.name)
            )

            results = query.all()

            # Group by period
            data_by_period = {}
            for row in results:
                period = row.period
                if period not in data_by_period:
                    data_by_period[period] = {"period": period, "areas": []}

                data_by_period[period]["areas"].append(
                    {
                        "area_id": row.area_id,
                        "area_name": row.area_name,
                        "area_color": row.area_color,
                        "order_count": row.order_count,
                        "total_sales": float(row.total_sales or 0),
                    }
                )

            # Sort periods and convert to list
            data = sorted(data_by_period.values(), key=lambda x: x["period"])

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "group_by": group_by,
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating areas trends report: {e}")
        return jsonify(
            error_response("Error al generar reporte de tendencias por área")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
