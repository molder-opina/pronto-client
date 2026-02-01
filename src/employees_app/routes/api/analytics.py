"""
Analytics API - Advanced analytics and KPIs for business intelligence

This module provides endpoints for comprehensive analytics including:
- Revenue trends and KPIs
- Customer retention metrics
- Waiter performance analysis
- Category performance
- Daily/weekly/monthly comparisons
- Customer lifetime value
- Repeat customer analysis
"""

from datetime import datetime, timedelta
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import Date, and_, case, cast, func

from shared.jwt_middleware import get_current_user, get_employee_id, jwt_required
from shared.constants import PaymentStatus
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Customer, Employee, MenuCategory, MenuItem, Order, OrderItem
from shared.security import decrypt_string
from shared.serializers import error_response, success_response

analytics_bp = Blueprint("analytics", __name__)
logger = get_logger(__name__)


@analytics_bp.get("/analytics/kpis")
@jwt_required
def get_kpis():
    """
    Obtiene KPIs principales del negocio.

    Query params:
    - start_date: YYYY-MM-DD (default: 7 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    - comparison_period: 'previous_period'|'same_period_last_year' (default: 'previous_period')
    """
    try:
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")
        comparison_period = request.args.get("comparison_period", "previous_period")

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
            period_length = (end_date - start_date).days + 1

            if comparison_period == "previous_period":
                prev_start_date = start_date - timedelta(days=period_length)
                prev_end_date = end_date - timedelta(days=period_length)
            else:
                prev_start_date = start_date - timedelta(days=365)
                prev_end_date = end_date - timedelta(days=365)

            def calculate_kpis(db, sd, ed):
                date_col = cast(Order.created_at, Date)

                total_orders = (
                    db.query(func.count(Order.id))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                )

                total_revenue = (
                    db.query(func.sum(Order.total_amount))
                    .filter(
                        and_(
                            date_col >= sd,
                            date_col <= ed,
                            Order.payment_status == PaymentStatus.PAID.value,
                        )
                    )
                    .scalar()
                    or 0
                )

                avg_order_value = (
                    db.query(func.avg(Order.total_amount))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                    or 0
                )

                total_customers = (
                    db.query(func.count(func.distinct(Order.customer_id)))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                )

                repeat_customers = (
                    db.query(func.count(func.distinct(Order.customer_id)))
                    .filter(
                        and_(
                            date_col >= sd,
                            date_col <= ed,
                            Order.customer_id.in_(
                                db.query(Order.customer_id)
                                .filter(cast(Order.created_at, Date) < sd)
                                .distinct()
                            ),
                        )
                    )
                    .scalar()
                    or 0
                )

                avg_preparation_time = (
                    db.query(
                        func.avg(
                            case(
                                (
                                    Order.ready_at.isnot(None),
                                    func.extract("epoch", Order.ready_at - Order.chef_accepted_at),
                                ),
                                else_=None,
                            )
                        )
                    )
                    .filter(
                        and_(
                            date_col >= sd,
                            date_col <= ed,
                            Order.chef_accepted_at.isnot(None),
                            Order.ready_at.isnot(None),
                        )
                    )
                    .scalar()
                )

                avg_delivery_time = (
                    db.query(
                        func.avg(
                            case(
                                (
                                    Order.delivered_at.isnot(None),
                                    func.extract("epoch", Order.delivered_at - Order.ready_at),
                                ),
                                else_=None,
                            )
                        )
                    )
                    .filter(
                        and_(
                            date_col >= sd,
                            date_col <= ed,
                            Order.ready_at.isnot(None),
                            Order.delivered_at.isnot(None),
                        )
                    )
                    .scalar()
                )

                total_tips = (
                    db.query(func.sum(Order.tip_amount))
                    .filter(
                        and_(
                            date_col >= sd,
                            date_col <= ed,
                            Order.payment_status == PaymentStatus.PAID.value,
                        )
                    )
                    .scalar()
                    or 0
                )

                return {
                    "total_orders": total_orders,
                    "total_revenue": float(total_revenue),
                    "avg_order_value": float(avg_order_value),
                    "total_customers": total_customers,
                    "repeat_customers": repeat_customers,
                    "repeat_customer_rate": (repeat_customers / total_customers * 100)
                    if total_customers > 0
                    else 0,
                    "avg_preparation_time_seconds": float(avg_preparation_time)
                    if avg_preparation_time
                    else None,
                    "avg_delivery_time_seconds": float(avg_delivery_time)
                    if avg_delivery_time
                    else None,
                    "total_tips": float(total_tips),
                }

            current_kpis = calculate_kpis(db, start_date, end_date)
            previous_kpis = calculate_kpis(db, prev_start_date, prev_end_date)

            def calculate_change(current, previous):
                if previous == 0:
                    return (
                        {"value": 0, "percentage": 0}
                        if current == 0
                        else {"value": current, "percentage": 100}
                    )
                change = current - previous
                return {"value": change, "percentage": (change / previous) * 100}

            kpis_with_changes = {
                "total_orders": {
                    "value": current_kpis["total_orders"],
                    "change": calculate_change(
                        current_kpis["total_orders"], previous_kpis["total_orders"]
                    ),
                },
                "total_revenue": {
                    "value": current_kpis["total_revenue"],
                    "change": calculate_change(
                        current_kpis["total_revenue"], previous_kpis["total_revenue"]
                    ),
                },
                "avg_order_value": {
                    "value": current_kpis["avg_order_value"],
                    "change": calculate_change(
                        current_kpis["avg_order_value"], previous_kpis["avg_order_value"]
                    ),
                },
                "total_customers": {
                    "value": current_kpis["total_customers"],
                    "change": calculate_change(
                        current_kpis["total_customers"], previous_kpis["total_customers"]
                    ),
                },
                "repeat_customer_rate": {
                    "value": current_kpis["repeat_customer_rate"],
                    "change": calculate_change(
                        current_kpis["repeat_customer_rate"], previous_kpis["repeat_customer_rate"]
                    ),
                },
                "avg_preparation_time_seconds": {
                    "value": current_kpis["avg_preparation_time_seconds"],
                    "change": None,
                },
                "avg_delivery_time_seconds": {
                    "value": current_kpis["avg_delivery_time_seconds"],
                    "change": None,
                },
                "total_tips": {
                    "value": current_kpis["total_tips"],
                    "change": calculate_change(
                        current_kpis["total_tips"], previous_kpis["total_tips"]
                    ),
                },
            }

            return jsonify(
                success_response(
                    {
                        "kpis": kpis_with_changes,
                        "period": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "days": period_length,
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating KPIs: {e}")
        return jsonify(error_response("Error al generar KPIs")), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/revenue-trends")
@jwt_required
def get_revenue_trends():
    """
    Obtiene tendencias de ingresos por hora, día y mes.

    Query params:
    - start_date: YYYY-MM-DD (default: 30 días atrás)
    - end_date: YYYY-MM-DD (default: hoy)
    - granularity: hour|day|week|month (default: day)
    """
    try:
        end_date_str = request.args.get("end_date")
        start_date_str = request.args.get("start_date")
        granularity = request.args.get("granularity", "day")

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
            if granularity == "hour":
                time_col = func.to_char(Order.created_at, "HH24:MI")
                order_col = func.to_char(Order.created_at, "YYYY-MM-DD")
            elif granularity == "day":
                time_col = func.to_char(Order.created_at, "YYYY-MM-DD")
                order_col = time_col
            elif granularity == "week":
                time_col = func.to_char(Order.created_at, 'IYYY-"W"IW')
                order_col = func.to_char(Order.created_at, 'IYYY-"W"IW')
            elif granularity == "month":
                time_col = func.to_char(Order.created_at, "YYYY-MM")
                order_col = time_col
            else:
                return jsonify(
                    error_response("Invalid granularity parameter")
                ), HTTPStatus.BAD_REQUEST

            query = (
                db.query(
                    time_col.label("time_period"),
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_revenue"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.sum(Order.tip_amount).label("total_tips"),
                )
                .filter(
                    and_(
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                    )
                )
                .group_by(time_col)
                .order_by(order_col)
            )

            results = query.all()

            data = []
            for row in results:
                data.append(
                    {
                        "time_period": row.time_period,
                        "order_count": row.order_count,
                        "total_revenue": float(row.total_revenue or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                        "total_tips": float(row.total_tips or 0),
                    }
                )

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "granularity": granularity,
                        },
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating revenue trends: {e}")
        return jsonify(
            error_response("Error al generar tendencias de ingresos")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/waiter-performance")
@jwt_required
def get_waiter_performance():
    """
    Obtiene análisis de rendimiento de meseros.

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
                    Employee.id,
                    Employee.name_encrypted,
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.sum(Order.tip_amount).label("total_tips"),
                    func.avg(Order.tip_amount).label("avg_tip"),
                    func.sum(
                        case(
                            (Order.payment_status == PaymentStatus.PAID.value, Order.total_amount),
                            else_=0,
                        )
                    ).label("total_revenue"),
                )
                .join(Order, Order.waiter_id == Employee.id)
                .filter(
                    and_(
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                    )
                )
                .group_by(Employee.id, Employee.name_encrypted)
                .order_by(func.sum(Order.total_amount).desc())
            )

            results = query.all()

            data = []
            for row in results:
                waiter_name = decrypt_string(row.name_encrypted) or f"Employee #{row.id}"

                avg_acceptance_time = (
                    db.query(
                        func.avg(func.extract("epoch", Order.waiter_accepted_at - Order.created_at))
                    )
                    .join(Employee, Order.waiter_id == Employee.id)
                    .filter(
                        and_(
                            Employee.id == row.id,
                            cast(Order.created_at, Date) >= start_date,
                            cast(Order.created_at, Date) <= end_date,
                            Order.waiter_accepted_at.isnot(None),
                        )
                    )
                    .scalar()
                )

                data.append(
                    {
                        "waiter_id": row.id,
                        "waiter_name": waiter_name,
                        "order_count": row.order_count,
                        "total_sales": float(row.total_sales or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                        "total_tips": float(row.total_tips or 0),
                        "avg_tip": float(row.avg_tip or 0),
                        "tip_percentage": (float(row.total_tips or 0) / float(row.total_sales or 1))
                        * 100
                        if row.total_sales
                        else 0,
                        "avg_acceptance_time_seconds": float(avg_acceptance_time)
                        if avg_acceptance_time
                        else None,
                    }
                )

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating waiter performance: {e}")
        return jsonify(
            error_response("Error al generar rendimiento de meseros")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/category-performance")
@jwt_required
def get_category_performance():
    """
    Obtiene rendimiento por categoría de menú.

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
                    MenuCategory.id,
                    MenuCategory.name,
                    func.sum(OrderItem.quantity).label("total_quantity"),
                    func.count(OrderItem.id).label("order_count"),
                    func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
                    func.avg(OrderItem.unit_price).label("avg_item_price"),
                )
                .join(MenuItem, MenuItem.category_id == MenuCategory.id)
                .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
                .join(Order, Order.id == OrderItem.order_id)
                .filter(
                    and_(
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                        Order.payment_status == PaymentStatus.PAID.value,
                    )
                )
                .group_by(MenuCategory.id, MenuCategory.name)
                .order_by(func.sum(OrderItem.quantity * OrderItem.unit_price).desc())
            )

            results = query.all()

            data = []
            for row in results:
                data.append(
                    {
                        "category_id": row.id,
                        "category_name": row.name,
                        "total_quantity": row.total_quantity,
                        "order_count": row.order_count,
                        "total_revenue": float(row.total_revenue or 0),
                        "avg_item_price": float(row.avg_item_price or 0),
                    }
                )

            total_revenue = sum(d["total_revenue"] for d in data)

            for item in data:
                item["revenue_percentage"] = (
                    (item["total_revenue"] / total_revenue * 100) if total_revenue > 0 else 0
                )

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating category performance: {e}")
        return jsonify(
            error_response("Error al generar rendimiento por categoría")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/customer-segments")
@jwt_required
def get_customer_segments():
    """
    Obtiene segmentación de clientes por valor y frecuencia.

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
                    Customer.id,
                    Customer.name_encrypted,
                    Customer.email_encrypted,
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_spent"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.min(Order.created_at).label("first_order_date"),
                    func.max(Order.created_at).label("last_order_date"),
                )
                .join(Order, Order.customer_id == Customer.id)
                .filter(
                    and_(
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                        Order.payment_status == PaymentStatus.PAID.value,
                    )
                )
                .group_by(Customer.id, Customer.name_encrypted, Customer.email_encrypted)
                .order_by(func.sum(Order.total_amount).desc())
            )

            results = query.all()

            data = []
            for row in results:
                customer_name = decrypt_string(row.name_encrypted) or "Unknown"
                customer_email = decrypt_string(row.email_encrypted) or "Unknown"

                order_frequency = row.order_count / max((end_date - start_date).days, 1)

                avg_days_between_orders = None
                if row.order_count > 1 and row.first_order_date and row.last_order_date:
                    days_span = (row.last_order_date.date() - row.first_order_date.date()).days
                    avg_days_between_orders = days_span / (row.order_count - 1)

                if row.total_spent >= 1000:
                    segment = "high_value"
                elif row.total_spent >= 500:
                    segment = "medium_value"
                else:
                    segment = "low_value"

                if row.order_count >= 10:
                    frequency = "high"
                elif row.order_count >= 5:
                    frequency = "medium"
                else:
                    frequency = "low"

                data.append(
                    {
                        "customer_id": row.id,
                        "customer_name": customer_name,
                        "customer_email": customer_email,
                        "order_count": row.order_count,
                        "total_spent": float(row.total_spent or 0),
                        "avg_order_value": float(row.avg_order_value or 0),
                        "first_order_date": row.first_order_date.strftime("%Y-%m-%d")
                        if row.first_order_date
                        else None,
                        "last_order_date": row.last_order_date.strftime("%Y-%m-%d")
                        if row.last_order_date
                        else None,
                        "order_frequency": order_frequency,
                        "avg_days_between_orders": avg_days_between_orders,
                        "segment": segment,
                        "frequency": frequency,
                    }
                )

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating customer segments: {e}")
        return jsonify(
            error_response("Error al generar segmentación de clientes")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/operational-metrics")
@jwt_required
def get_operational_metrics():
    """
    Obtiene métricas operativas: tiempos de preparación, entrega y servicio.

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
            date_col = cast(Order.created_at, Date)

            preparation_times = (
                db.query(
                    func.avg(func.extract("epoch", Order.ready_at - Order.chef_accepted_at)).label(
                        "avg_seconds"
                    ),
                    func.min(func.extract("epoch", Order.ready_at - Order.chef_accepted_at)).label(
                        "min_seconds"
                    ),
                    func.max(func.extract("epoch", Order.ready_at - Order.chef_accepted_at)).label(
                        "max_seconds"
                    ),
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.chef_accepted_at.isnot(None),
                        Order.ready_at.isnot(None),
                    )
                )
                .first()
            )

            delivery_times = (
                db.query(
                    func.avg(func.extract("epoch", Order.delivered_at - Order.ready_at)).label(
                        "avg_seconds"
                    ),
                    func.min(func.extract("epoch", Order.delivered_at - Order.ready_at)).label(
                        "min_seconds"
                    ),
                    func.max(func.extract("epoch", Order.delivered_at - Order.ready_at)).label(
                        "max_seconds"
                    ),
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.ready_at.isnot(None),
                        Order.delivered_at.isnot(None),
                    )
                )
                .first()
            )

            waiter_acceptance_times = (
                db.query(
                    func.avg(
                        func.extract("epoch", Order.waiter_accepted_at - Order.created_at)
                    ).label("avg_seconds"),
                    func.min(
                        func.extract("epoch", Order.waiter_accepted_at - Order.created_at)
                    ).label("min_seconds"),
                    func.max(
                        func.extract("epoch", Order.waiter_accepted_at - Order.created_at)
                    ).label("max_seconds"),
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.waiter_accepted_at.isnot(None),
                    )
                )
                .first()
            )

            chef_acceptance_times = (
                db.query(
                    func.avg(
                        func.extract("epoch", Order.chef_accepted_at - Order.created_at)
                    ).label("avg_seconds"),
                    func.min(
                        func.extract("epoch", Order.chef_accepted_at - Order.created_at)
                    ).label("min_seconds"),
                    func.max(
                        func.extract("epoch", Order.chef_accepted_at - Order.created_at)
                    ).label("max_seconds"),
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.chef_accepted_at.isnot(None),
                    )
                )
                .first()
            )

            total_orders = (
                db.query(func.count(Order.id))
                .filter(date_col >= start_date)
                .filter(date_col <= end_date)
                .scalar()
            )

            delivered_orders = (
                db.query(func.count(Order.id))
                .filter(
                    and_(
                        date_col >= start_date, date_col <= end_date, Order.delivered_at.isnot(None)
                    )
                )
                .scalar()
            )

            data = {
                "preparation_time": {
                    "avg_seconds": float(preparation_times.avg_seconds)
                    if preparation_times.avg_seconds
                    else None,
                    "min_seconds": float(preparation_times.min_seconds)
                    if preparation_times.min_seconds
                    else None,
                    "max_seconds": float(preparation_times.max_seconds)
                    if preparation_times.max_seconds
                    else None,
                },
                "delivery_time": {
                    "avg_seconds": float(delivery_times.avg_seconds)
                    if delivery_times.avg_seconds
                    else None,
                    "min_seconds": float(delivery_times.min_seconds)
                    if delivery_times.min_seconds
                    else None,
                    "max_seconds": float(delivery_times.max_seconds)
                    if delivery_times.max_seconds
                    else None,
                },
                "waiter_acceptance_time": {
                    "avg_seconds": float(waiter_acceptance_times.avg_seconds)
                    if waiter_acceptance_times.avg_seconds
                    else None,
                    "min_seconds": float(waiter_acceptance_times.min_seconds)
                    if waiter_acceptance_times.min_seconds
                    else None,
                    "max_seconds": float(waiter_acceptance_times.max_seconds)
                    if waiter_acceptance_times.max_seconds
                    else None,
                },
                "chef_acceptance_time": {
                    "avg_seconds": float(chef_acceptance_times.avg_seconds)
                    if chef_acceptance_times.avg_seconds
                    else None,
                    "min_seconds": float(chef_acceptance_times.min_seconds)
                    if chef_acceptance_times.min_seconds
                    else None,
                    "max_seconds": float(chef_acceptance_times.max_seconds)
                    if chef_acceptance_times.max_seconds
                    else None,
                },
                "delivery_rate": {
                    "total_orders": total_orders,
                    "delivered_orders": delivered_orders,
                    "percentage": (delivered_orders / total_orders * 100)
                    if total_orders > 0
                    else 0,
                },
            }

            return jsonify(
                success_response(
                    {
                        "data": data,
                        "filters": {"start_date": str(start_date), "end_date": str(end_date)},
                    }
                )
            ), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating operational metrics: {e}")
        return jsonify(
            error_response("Error al generar métricas operativas")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@analytics_bp.get("/analytics/comparison")
@jwt_required
def get_comparison():
    """
    Compara dos períodos de tiempo específicos.

    Query params:
    - current_start_date: YYYY-MM-DD (required)
    - current_end_date: YYYY-MM-DD (required)
    - previous_start_date: YYYY-MM-DD (optional, defaults to same length before current period)
    - previous_end_date: YYYY-MM-DD (optional)
    """
    try:
        current_start_date_str = request.args.get("current_start_date")
        current_end_date_str = request.args.get("current_end_date")
        previous_start_date_str = request.args.get("previous_start_date")
        previous_end_date_str = request.args.get("previous_end_date")

        if not current_start_date_str or not current_end_date_str:
            return jsonify(
                error_response("current_start_date and current_end_date are required")
            ), HTTPStatus.BAD_REQUEST

        current_start_date = datetime.strptime(current_start_date_str, "%Y-%m-%d").date()
        current_end_date = datetime.strptime(current_end_date_str, "%Y-%m-%d").date()

        if previous_start_date_str and previous_end_date_str:
            previous_start_date = datetime.strptime(previous_start_date_str, "%Y-%m-%d").date()
            previous_end_date = datetime.strptime(previous_end_date_str, "%Y-%m-%d").date()
        else:
            period_length = (current_end_date - current_start_date).days + 1
            previous_start_date = current_start_date - timedelta(days=period_length)
            previous_end_date = current_end_date - timedelta(days=period_length)

        with get_session() as db:

            def calculate_metrics(db, sd, ed):
                date_col = cast(Order.created_at, Date)

                total_orders = (
                    db.query(func.count(Order.id))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                )

                total_revenue = (
                    db.query(func.sum(Order.total_amount))
                    .filter(and_(date_col >= sd, date_col <= ed, Order.payment_status == "paid"))
                    .scalar()
                    or 0
                )

                avg_order_value = (
                    db.query(func.avg(Order.total_amount))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                    or 0
                )

                total_customers = (
                    db.query(func.count(func.distinct(Order.customer_id)))
                    .filter(and_(date_col >= sd, date_col <= ed))
                    .scalar()
                )

                total_tips = (
                    db.query(func.sum(Order.tip_amount))
                    .filter(and_(date_col >= sd, date_col <= ed, Order.payment_status == "paid"))
                    .scalar()
                    or 0
                )

                return {
                    "total_orders": total_orders,
                    "total_revenue": float(total_revenue),
                    "avg_order_value": float(avg_order_value),
                    "total_customers": total_customers,
                    "total_tips": float(total_tips),
                }

            current_metrics = calculate_metrics(db, current_start_date, current_end_date)
            previous_metrics = calculate_metrics(db, previous_start_date, previous_end_date)

            def calculate_change(current, previous):
                if previous == 0:
                    return 100 if current > 0 else 0
                return ((current - previous) / previous) * 100

            comparison = {
                "current_period": {
                    "start_date": str(current_start_date),
                    "end_date": str(current_end_date),
                    "metrics": current_metrics,
                },
                "previous_period": {
                    "start_date": str(previous_start_date),
                    "end_date": str(previous_end_date),
                    "metrics": previous_metrics,
                },
                "changes": {
                    "total_orders": calculate_change(
                        current_metrics["total_orders"], previous_metrics["total_orders"]
                    ),
                    "total_revenue": calculate_change(
                        current_metrics["total_revenue"], previous_metrics["total_revenue"]
                    ),
                    "avg_order_value": calculate_change(
                        current_metrics["avg_order_value"], previous_metrics["avg_order_value"]
                    ),
                    "total_customers": calculate_change(
                        current_metrics["total_customers"], previous_metrics["total_customers"]
                    ),
                    "total_tips": calculate_change(
                        current_metrics["total_tips"], previous_metrics["total_tips"]
                    ),
                },
            }

            return jsonify(success_response(comparison)), HTTPStatus.OK

    except ValueError as e:
        return jsonify(error_response(f"Invalid date format: {e!s}")), HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.error(f"Error generating comparison: {e}")
        return jsonify(
            error_response("Error al generar comparación")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
