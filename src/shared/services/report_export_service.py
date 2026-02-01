"""
Service for exporting reports to CSV and Excel formats.
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO

from flask import Blueprint
from sqlalchemy import Date, and_, cast, func, select

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import MenuItem, Order

reports_bp = Blueprint("reports", __name__)
logger = get_logger(__name__)


class ReportExportService:
    """Service for exporting reports to CSV and Excel formats."""

    @staticmethod
    def export_sales_report_to_csv(start_date: str, end_date: str) -> bytes:
        """
        Export sales report to CSV format.

        Returns CSV file bytes for download.
        """
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

            with get_session() as session:
                query = (
                    select(
                        Order.id,
                        cast(Order.created_at, Date).label("date"),
                        func.count(Order.id).label("order_count"),
                        func.sum(Order.total_amount).label("total_sales"),
                        func.sum(Order.tip_amount).label("total_tips"),
                        func.avg(Order.total_amount).label("avg_order_value"),
                    )
                    .where(
                        and_(
                            cast(Order.created_at, Date) >= start_date,
                            cast(Order.created_at, Date) <= end_date,
                            Order.payment_status == "paid",
                        )
                    )
                    .group_by(cast(Order.created_at, Date))
                    .order_by(cast(Order.created_at, Date))
                )

            results = session.execute(query).all()

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

            # Generate CSV
            csv_buffer = StringIO()
            if data:
                csv_buffer.write(",".join(data[0].keys()) + "\n")
                for row in data:
                    csv_buffer.write(
                        ",".join(
                            [
                                str(row["date"]),
                                str(row["order_count"]),
                                f"{row['total_sales']:.2f}",
                                f"{row['total_tips']:.2f}",
                                f"{row['avg_order_value']:.2f}",
                            ]
                        )
                        + "\n"
                    )

            return csv_buffer.getvalue().encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating CSV export: {e}")
            return b""

    @staticmethod
    def export_sales_report_to_excel(
        start_date: str, end_date: str, alguna: str = "excel"
    ) -> bytes:
        """
        Export sales report to Excel format.

        Returns Excel file bytes for download.
        """
        try:
            if alguna == "excel":
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

                with get_session() as session:
                    query = (
                        select(
                            Order.id,
                            cast(Order.created_at, Date).label("date"),
                            func.sum(Order.total_amount).label("total_sales"),
                            func.sum(Order.tip_amount).label("total_tips"),
                            func.avg(Order.total_amount).label("avg_order_value"),
                        )
                        .where(
                            and_(
                                cast(Order.created_at, Date) >= start_date,
                                cast(Order.created_at, Date) <= end_date,
                                Order.payment_status == "paid",
                            )
                        )
                        .group_by(cast(Order.created_at, Date))
                        .order_by(cast(Order.created_at, Date))
                    )

                results = session.execute(query).all()

                # Generate CSV (fallback to CSV if excel is not available)
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

                # Generate CSV
                csv_buffer = StringIO()
                if data:
                    csv_buffer.write(",".join(data[0].keys()) + "\n")
                    for row in data:
                        csv_buffer.write(
                            ",".join(
                                [
                                    str(row["date"]),
                                    str(row["order_count"]),
                                    f"{row['total_sales']:.2f}",
                                    f"{row['total_tips']:.2f}",
                                    f"{row['avg_order_value']:.2f}",
                                ]
                            )
                            + "\n"
                        )

                return csv_buffer.getvalue().encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating Excel export: {e}")
            return b""

    @staticmethod
    def export_inventory_report_to_csv() -> bytes:
        """
        Export inventory report to CSV format.

        Returns CSV file bytes for download.
        """
        try:
            with get_session() as session:
                # Get all menu items with stock levels
                items = session.query(MenuItem).all()

                data = []
                for item in items:
                    data.append(
                        {
                            "id": item.id,
                            "name": item.name,
                            "category_id": item.category_id,
                            "current_stock": item.current_stock or 0,
                            "unit": item.unit or "unidad",
                            "price": float(item.price or 0),
                            "supplier": item.supplier or "",
                        }
                    )

                # Generate CSV
                csv_buffer = StringIO()
                if data:
                    csv_buffer.write(",".join(data[0].keys()) + "\n")
                    for row in data:
                        csv_buffer.write(
                            ",".join(
                                [
                                    str(row["id"]),
                                    row["name"],
                                    row["category_id"],
                                    str(row["current_stock"]),
                                    row["unit"],
                                    f"{row['price']:.2f}",
                                    row["supplier"],
                                ]
                            )
                            + "\n"
                        )

                return csv_buffer.getvalue().encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating inventory export: {e}")
            return b""

    @staticmethod
    def export_employee_performance_report_to_csv(
        employee_id: int, start_date: str, end_date: str
    ) -> bytes:
        """
        Export employee performance report to CSV format.

        Returns CSV file bytes for download.
        """
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

            with get_session() as session:
                query = (
                    select(
                        Order.id,
                        cast(Order.created_at, Date).label("date"),
                        func.count(Order.id).label("order_count"),
                        func.sum(Order.total_amount).label("total_sales"),
                    ).where(
                        and_(
                            (Order.waiter_id == employee_id)
                            | (Order.chef_id == employee_id)
                            | (Order.delivery_waiter_id == employee_id),
                            cast(Order.created_at, Date) >= start_date,
                            cast(Order.created_at, Date) <= end_date,
                        )
                    )
                ).order_by(cast(Order.created_at, Date))

                results = session.execute(query).all()

                data = []
                for row in results:
                    data.append(
                        {
                            "date": str(row.date),
                            "order_count": row.order_count,
                            "total_sales": float(row.total_sales or 0),
                            "orders_count": len(results),
                        }
                    )

                # Generate CSV
                csv_buffer = StringIO()
                if data:
                    csv_buffer.write(",".join(data[0].keys()) + "\n")
                    for row in data:
                        csv_buffer.write(
                            ",".join(
                                [
                                    str(row["date"]),
                                    str(row["order_count"]),
                                    f"{row['total_sales']:.2f}",
                                    str(row["orders_count"]),
                                ]
                            )
                            + "\n"
                        )

                return csv_buffer.getvalue().encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating employee performance export: {e}")
            return b""
