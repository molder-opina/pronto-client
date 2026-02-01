"""
Analytics Service - Business intelligence and KPI calculations

This service provides comprehensive analytics functions for:
- Revenue trends and KPIs
- Customer retention metrics
- Waiter performance analysis
- Category performance
- Daily/weekly/monthly comparisons
- Customer lifetime value
- Repeat customer analysis
- Operational metrics
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, and_, case, cast, func
from sqlalchemy.orm import Session

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import (
    Customer,
    Employee,
    MenuCategory,
    MenuItem,
    Order,
    OrderItem,
)
from shared.security import decrypt_string

logger = get_logger(__name__)


class AnalyticsService:
    """Service for calculating business analytics and KPIs."""

    @staticmethod
    def get_kpis(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> dict[str, Any]:
        """
        Calculate KPIs for a given date range.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session (will create one if not provided)

        Returns:
            Dictionary containing KPIs: total_orders, total_revenue, avg_order_value,
            total_customers, repeat_customers, repeat_customer_rate, avg_preparation_time_seconds,
            avg_delivery_time_seconds, total_tips
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            date_col = cast(Order.created_at, Date)

            total_orders = (
                db_session.query(func.count(Order.id))
                .filter(and_(date_col >= start_date, date_col <= end_date))
                .scalar()
            )

            total_revenue = (
                db_session.query(func.sum(Order.total_amount))
                .filter(
                    and_(
                        date_col >= start_date, date_col <= end_date, Order.payment_status == "paid"
                    )
                )
                .scalar()
                or 0
            )

            avg_order_value = (
                db_session.query(func.avg(Order.total_amount))
                .filter(and_(date_col >= start_date, date_col <= end_date))
                .scalar()
                or 0
            )

            total_customers = (
                db_session.query(func.count(func.distinct(Order.customer_id)))
                .filter(and_(date_col >= start_date, date_col <= end_date))
                .scalar()
            )

            repeat_customers = (
                db_session.query(func.count(func.distinct(Order.customer_id)))
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.customer_id.in_(
                            db_session.query(Order.customer_id)
                            .filter(cast(Order.created_at, Date) < start_date)
                            .distinct()
                        ),
                    )
                )
                .scalar()
                or 0
            )

            avg_preparation_time = (
                db_session.query(
                    func.avg(
                        case(
                            [
                                (
                                    Order.ready_at.isnot(None),
                                    func.extract("epoch", Order.ready_at - Order.chef_accepted_at),
                                )
                            ],
                            else_=None,
                        )
                    )
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.chef_accepted_at.isnot(None),
                        Order.ready_at.isnot(None),
                    )
                )
                .scalar()
            )

            avg_delivery_time = (
                db_session.query(
                    func.avg(
                        case(
                            [
                                (
                                    Order.delivered_at.isnot(None),
                                    func.extract("epoch", Order.delivered_at - Order.ready_at),
                                )
                            ],
                            else_=None,
                        )
                    )
                )
                .filter(
                    and_(
                        date_col >= start_date,
                        date_col <= end_date,
                        Order.ready_at.isnot(None),
                        Order.delivered_at.isnot(None),
                    )
                )
                .scalar()
            )

            total_tips = (
                db_session.query(func.sum(Order.tip_amount))
                .filter(
                    and_(
                        date_col >= start_date, date_col <= end_date, Order.payment_status == "paid"
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
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_revenue_trends(
        start_date: date,
        end_date: date,
        granularity: str = "day",
        db_session: Session | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get revenue trends by time period.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            granularity: hour, day, week, or month
            db_session: Optional database session

        Returns:
            List of dictionaries with time_period, order_count, total_revenue,
            avg_order_value, and total_tips
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
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
                raise ValueError(f"Invalid granularity: {granularity}")

            query = (
                db_session.query(
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

            return data
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_waiter_performance(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> list[dict[str, Any]]:
        """
        Get waiter performance metrics.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            List of dictionaries with waiter_id, waiter_name, order_count, total_sales,
            avg_order_value, total_tips, avg_tip, tip_percentage, avg_acceptance_time_seconds
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
                    Employee.id,
                    Employee.name_encrypted,
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.sum(Order.tip_amount).label("total_tips"),
                    func.avg(Order.tip_amount).label("avg_tip"),
                    func.sum(
                        case([(Order.payment_status == "paid", Order.total_amount)], else_=0)
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
                    db_session.query(
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

            return data
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_category_performance(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> list[dict[str, Any]]:
        """
        Get category performance metrics.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            List of dictionaries with category_id, category_name, total_quantity,
            order_count, total_revenue, avg_item_price, revenue_percentage
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
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
                        Order.payment_status == "paid",
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

            return data
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_customer_segments(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> list[dict[str, Any]]:
        """
        Get customer segmentation by value and frequency.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            List of dictionaries with customer_id, customer_name, customer_email,
            order_count, total_spent, avg_order_value, first_order_date,
            last_order_date, order_frequency, avg_days_between_orders, segment, frequency
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
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
                        Order.payment_status == "paid",
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

            return data
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_operational_metrics(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> dict[str, Any]:
        """
        Get operational metrics: preparation, delivery, and service times.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            Dictionary with preparation_time, delivery_time, waiter_acceptance_time,
            chef_acceptance_time (each with avg, min, max), and delivery_rate
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            date_col = cast(Order.created_at, Date)

            preparation_times = (
                db_session.query(
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
                db_session.query(
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
                db_session.query(
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
                db_session.query(
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
                db_session.query(func.count(Order.id))
                .filter(date_col >= start_date)
                .filter(date_col <= end_date)
                .scalar()
            )

            delivered_orders = (
                db_session.query(func.count(Order.id))
                .filter(
                    and_(
                        date_col >= start_date, date_col <= end_date, Order.delivered_at.isnot(None)
                    )
                )
                .scalar()
            )

            return {
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
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_top_products(
        start_date: date, end_date: date, limit: int = 10, db_session: Session | None = None
    ) -> list[dict[str, Any]]:
        """
        Get top products by quantity sold.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            limit: Maximum number of products to return
            db_session: Optional database session

        Returns:
            List of dictionaries with id, name, total_quantity, order_count, total_revenue
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
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
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                        Order.payment_status == "paid",
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

            return data
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_peak_hours(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        Get peak hours analysis showing order volume by hour of day.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            Tuple of (data list, peak hour dict)
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            hour_col = func.to_char(Order.created_at, "HH24")
            query = (
                db_session.query(
                    hour_col.label("hour"),
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_sales"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                )
                .filter(
                    and_(
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                    )
                )
                .group_by(hour_col)
                .order_by(hour_col)
            )

            results = query.all()

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

            peak_hour = max(data, key=lambda x: x["order_count"]) if data else None

            return data, peak_hour
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_waiter_tips(
        start_date: date, end_date: date, db_session: Session | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Get waiter tips report.

        Args:
            start_date: Start date for the period
            end_date: End date for the period
            db_session: Optional database session

        Returns:
            Tuple of (data list, summary dict)
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
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
                        cast(Order.created_at, Date) >= start_date,
                        cast(Order.created_at, Date) <= end_date,
                        Order.payment_status == "paid",
                        Order.tip_amount > 0,
                    )
                )
                .group_by(Employee.id, Employee.name_encrypted)
                .order_by(func.sum(Order.tip_amount).desc())
            )

            results = query.all()

            data = []
            for row in results:
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

            summary = {"total_tips": total_tips, "waiter_count": len(data)}

            return data, summary
        finally:
            if not session_provided:
                db.__exit__(None, None, None)

    @staticmethod
    def get_customer_lifetime_value(
        customer_id: int, db_session: Session | None = None
    ) -> dict[str, Any]:
        """
        Calculate customer lifetime value metrics.

        Args:
            customer_id: Customer ID
            db_session: Optional database session

        Returns:
            Dictionary with total_orders, total_spent, avg_order_value,
            first_order_date, last_order_date, days_active, avg_days_between_orders
        """
        session_provided = db_session is not None
        if not session_provided:
            db = get_session()
            db_session = db.__enter__()

        try:
            query = (
                db_session.query(
                    func.count(Order.id).label("total_orders"),
                    func.sum(Order.total_amount).label("total_spent"),
                    func.avg(Order.total_amount).label("avg_order_value"),
                    func.min(Order.created_at).label("first_order_date"),
                    func.max(Order.created_at).label("last_order_date"),
                )
                .filter(and_(Order.customer_id == customer_id, Order.payment_status == "paid"))
                .first()
            )

            if not query or query.total_orders == 0:
                return {
                    "total_orders": 0,
                    "total_spent": 0,
                    "avg_order_value": 0,
                    "first_order_date": None,
                    "last_order_date": None,
                    "days_active": 0,
                    "avg_days_between_orders": None,
                }

            days_active = (query.last_order_date.date() - query.first_order_date.date()).days + 1

            avg_days_between_orders = None
            if query.total_orders > 1:
                avg_days_between_orders = days_active / (query.total_orders - 1)

            return {
                "total_orders": query.total_orders,
                "total_spent": float(query.total_spent or 0),
                "avg_order_value": float(query.avg_order_value or 0),
                "first_order_date": query.first_order_date.strftime("%Y-%m-%d")
                if query.first_order_date
                else None,
                "last_order_date": query.last_order_date.strftime("%Y-%m-%d")
                if query.last_order_date
                else None,
                "days_active": days_active,
                "avg_days_between_orders": avg_days_between_orders,
            }
        finally:
            if not session_provided:
                db.__exit__(None, None, None)
