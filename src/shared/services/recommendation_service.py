"""
Service for generating customer recommendations based on order history.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import MenuItem, Order, OrderItem

logger = get_logger(__name__)


class RecommendationService:
    """Service for personalized product recommendations."""

    @staticmethod
    def get_personalized_recommendations(customer_id: int, limit: int = 6) -> list[dict[str, Any]]:
        """
        Get personalized recommendations based on customer's order history.

        Strategy:
        - Frequently ordered items (40% weight)
        - Recently ordered items (30% weight)
        - Items from popular categories (20% weight)
        - Items commonly ordered together (10% weight)
        """
        with get_session() as session:
            # Get customer's order history
            orders = (
                session.execute(
                    select(Order.id)
                    .where(Order.customer_id == customer_id)
                    .order_by(Order.created_at.desc())
                    .limit(20)
                )
                .scalars()
                .all()
            )

            if not orders:
                return []

            # Extract all ordered item IDs
            ordered_item_ids = set()
            for order in orders:
                for item in order.items:
                    ordered_item_ids.add(item.menu_item_id)

            # Get most frequent items
            frequent_items = session.execute(
                select(OrderItem.menu_item_id, func.count(OrderItem.id).label("frequency"))
                .where(OrderItem.menu_item_id.in_(ordered_item_ids))
                .group_by(OrderItem.menu_item_id)
                .order_by(desc("frequency"))
                .limit(limit)
            ).all()

            # Get recently ordered items
            recent_items = (
                session.execute(
                    select(OrderItem.menu_item_id)
                    .join(Order, OrderItem.order_id == Order.id)
                    .where(Order.customer_id == customer_id)
                    .order_by(Order.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )

            # Get popular categories
            popular_category_ids = (
                session.execute(
                    select(MenuItem.category_id, func.count(MenuItem.id).label("category_count"))
                    .join(MenuItem, OrderItem.order_id == MenuItem.id)
                    .where(Order.customer_id == customer_id)
                    .group_by(MenuItem.category_id)
                    .order_by(desc("category_count"))
                    .limit(5)
                )
                .scalars()
                .all()
            )

            # Get items commonly ordered together
            co_occurrences = session.execute(
                select(OrderItem.menu_item_id, func.count(OrderItem.id).label("co_count"))
                .where(
                    and_(
                        OrderItem.menu_item_id.in_(ordered_item_ids),
                        OrderItem.order_id.in_([o.id for o in orders if o.id != Order.id]),
                    )
                )
                .group_by(OrderItem.order_id)
                .having(func.count(OrderItem.id) > 1)
                .limit(10)
            ).all()

            # Calculate recommendation scores
            item_scores = {}

            # Score: Frequency (40%)
            for item in frequent_items[: int(limit * 0.4)]:
                item_scores[item.menu_item_id] = 40

            # Score: Recency (30%)
            for item in recent_items[: int(limit * 0.3)]:
                menu_item_id = item.menu_item_id
                days_ago = (datetime.utcnow() - item.created_at).days
                recency_score = max(0, 30 - days_ago)
                item_scores[menu_item_id] = item_scores.get(menu_item_id, 0) + recency_score

            # Score: Popular categories (20%)
            for item_id in popular_category_ids:
                item_scores.get(item_id, 0) + 20

            # Score: Co-occurrences (10%)
            for menu_item_id, co_count in co_occurrences:
                item_scores[menu_item_id] = item_scores.get(menu_item_id, 0) + co_count
                co_occurrence_ids = [
                    menu_item_id for menu_item_id, co_count in co_occurrences if co_count > 1
                ]
                for co_menu_item_id in co_occurrence_ids:
                    item_scores[co_menu_item_id] = item_scores.get(co_menu_item_id, 0) + 10

            # Sort by score and return
            sorted_items = sorted(item_scores.items(), key=lambda x: x[1], reverse=True)

            # Get item details
            item_ids = [item_id for item_id, _ in sorted_items[:limit]]

            items = session.execute(select(MenuItem).where(MenuItem.id.in_(item_ids)).all())

            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category_id": item.category_id,
                    "image_url": item.image_url,
                    "recommendation_score": item_scores[item.id],
                    "recommendation_reason": RecommendationService._get_recommendation_reason(
                        item_scores[item.id], item
                    ),
                }
                for item in items
            ]

    @staticmethod
    def get_trending_items(days: int = 7, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get trending items across all customers.

        Query params:
        - days: Number of days to analyze
        - limit: Maximum results
        """
        with get_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)

            query = (
                select(OrderItem.menu_item_id, func.count(OrderItem.id).label("order_count"))
                .join(Order, OrderItem.order_id == Order.id)
                .join(MenuItem, OrderItem.menu_item_id == MenuItem.id)
                .where(Order.created_at >= since_date)
                .join(MenuItem, OrderItem.order_id == Order.id)
                .group_by(OrderItem.menu_item_id)
                .order_by(desc("order_count"))
                .limit(limit)
            )

            results = session.execute(query).all()

            data = []
            for result in results:
                data.append(
                    {
                        "menu_item_id": result.menu_item_id,
                        "order_count": result.order_count,
                        "trending_days": days,
                    }
                )

            # Fetch item details
            item_ids = [d["menu_item_id"] for d in data]
            items = session.execute(select(MenuItem).where(MenuItem.id.in_(item_ids)).all())

            {item.id: item for item in items}

            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category_id": item.category_id,
                    "image_url": item.image_url,
                    "order_count": data["order_count"],
                }
                for item in items
            ]

    @staticmethod
    def get_complementary_items(menu_item_id: int) -> list[dict[str, Any]]:
        """
        Get items that are frequently ordered together with a given item.

        Useful for "Customers who bought this also bought X" feature.
        """
        with get_session() as session:
            # Find orders containing this item
            orders_with_item = session.execute(
                select(Order.id)
                .join(OrderItem, OrderItem.order_id == Order.id)
                .where(OrderItem.menu_item_id == menu_item_id)
                .scalars()
                .all()
            )

            if not orders_with_item:
                return []

            # Get all other items from those orders
            other_item_ids = (
                session.execute(
                    select(OrderItem.menu_item_id).where(
                        OrderItem.order_id.in_([o.id for o in orders_with_item])
                    )
                )
                .scalars()
                .all()
            )

            # Count frequency
            item_counts = {}
            for item_id in other_item_ids:
                item_counts[item_id] = item_counts.get(item_id, 0) + 1

            # Sort by frequency
            sorted_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)

            # Get top 3 complementary items
            top_complementary_ids = [
                item_id for item_id, _ in sorted_items[:3] if item_id != menu_item_id
            ]

            if not top_complementary_ids:
                return []

            # Fetch item details
            items = session.execute(
                select(MenuItem).where(MenuItem.id.in_(top_complementary_ids)).all()
            )

            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category_id": item.category_id,
                    "image_url": item.image_url,
                    "co_occurrence_count": item_counts[item_id],
                }
                for item in items
            ]

    @staticmethod
    def get_seasonal_recommendations() -> list[dict[str, Any]]:
        """
        Get seasonal recommendations based on current date/time.

        Examples:
        - Morning: Coffee, pastries
        - Afternoon: Lunch items, sandwiches
        - Evening: Dinner items, alcohol
        - Weekends: Special menu items
        """
        now = datetime.utcnow()
        hour = now.hour
        day_of_week = now.weekday()

        seasonal_items = []

        with get_session() as session:
            # Time-based recommendations
            if 5 <= hour < 11 or 11 <= hour < 14 or 14 <= hour < 17:  # Morning
                query = session.query(MenuItem).where(MenuItem.is_available)
            else:  # Evening
                query = session.query(MenuItem).where(MenuItem.is_available)

            # Day-based recommendations
            if day_of_week >= 5:  # Weekend
                query = session.query(MenuItem).where(MenuItem.is_weekend_special)
            elif day_of_week == 0:  # Monday
                query = session.query(MenuItem).where(MenuItem.is_weekday_special)

            # Limit to 10 items
            query = query.limit(10)

            items = query.all()

            for item in items:
                seasonal_items.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "price": float(item.price),
                        "category_id": item.category_id,
                        "image_url": item.image_url,
                        "recommendation_type": "seasonal",
                        "recommendation_context": RecommendationService._get_seasonal_context(
                            hour, day_of_week
                        ),
                    }
                )

            return seasonal_items

    @staticmethod
    def _get_seasonal_context(hour: int, day_of_week: int) -> str:
        """Get contextual description for seasonal recommendation."""
        day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        if 0 <= day_of_week < len(day_names):
            return f"{day_names[day_of_week]} habitual"
        return f"{day_names[min(day_of_week, 6)]} {day_names[min(day_of_week + 1, 6)]} especial"

    @staticmethod
    def _get_recommendation_reason(score: int, item: dict[str, Any]) -> str:
        """Get human-readable reason for recommendation."""
        if score >= 60:
            return "Muy pedido por ti"
        elif score >= 40:
            return "Frecuentemente pedido"
        elif score >= 30:
            return "Popular en su categoría"
        elif score >= 20:
            return "Tendencia actual"
        elif score >= 10:
            return "Pedido frecuente con este"
        else:
            return "Nueva sugerencia"
