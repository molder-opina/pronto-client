"""
Enhanced search service with intelligent filters.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Category, MenuItem

logger = get_logger(__name__)


class EnhancedSearchService:
    """Service for advanced search with multiple filters."""

    @staticmethod
    def search_with_filters(
        query: str,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        dietary: list[str] | None = None,
        spice_level: str | None = None,
        sort_by: str = "popularity",
        in_stock_only: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Advanced search with multiple filters.

        Query params:
        - query: Search text
        - category: Filter by menu category
        - min_price: Minimum price filter
        - max_price: Maximum price filter
        - dietary: Dietary restrictions (vegetarian, vegan, gluten-free)
        - spice_level: Spice preference (mild, medium, hot, very-hot)
        - sort_by: Sort results by popularity (popularity, price_asc, price_desc, name_asc)
        - in_stock_only: Only show items in stock
        - limit: Maximum results

        Returns:
            List of matching items with filters applied
        """
        with get_session():
            # Start building base query
            query = select(MenuItem).where(MenuItem.is_available)

            # Apply text search filter
            if query:
                search_pattern = f"%{query}%"
                query = query.where(MenuItem.name.ilike(search_pattern))

            # Apply category filter
            if category:
                query = query.where(MenuItem.category_id == int(category))

            # Apply dietary filters
            if dietary:
                if "vegetarian" in dietary:
                    query = query.where(MenuItem.is_vegetarian)
                if "vegan" in dietary:
                    query = query.where(MenuItem.is_vegan)
                if "gluten-free" in dietary:
                    query = query.where(MenuItem.is_gluten_free)

            # Apply price range filter
            if min_price is not None:
                query = query.where(MenuItem.price >= min_price)
            if max_price is not None:
                query = query.where(MenuItem.price <= max_price)

            # Apply spice level filter
            if spice_level:
                spice_map = {"mild": 1, "medium": 2, "hot": 3, "very-hot": 4}
                if spice_level in spice_map:
                    query = query.where(MenuItem.spice_level == spice_map[spice_level])

            # Apply stock filter
            if in_stock_only:
                query = query.where(MenuItem.current_stock > 0)

            # Sort results
            if sort_by == "popularity":
                query = query.order_by(MenuItem.popularity_score.desc())
            elif sort_by == "price_asc":
                query = query.order_by(MenuItem.price.asc())
            elif sort_by == "price_desc":
                query = query.order_by(MenuItem.price.desc())
            elif sort_by == "name_asc":
                query = query.order_by(MenuItem.name.asc())

            # Apply limit
            if limit:
                query = query.limit(limit)

            results = query.all()

            data = [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description or "",
                    "price": float(item.price or 0),
                    "category_id": item.category_id,
                    "image_url": item.image_url or "",
                    "current_stock": item.current_stock or 0,
                    "unit": item.unit or "pieza",
                    "is_vegetarian": item.is_vegetarian or False,
                    "is_vegan": item.is_vegan or False,
                    "is_gluten_free": item.is_gluten_free or False,
                    "spice_level": item.spice_level or 1,
                    "popularity_score": item.popularity_score or 0,
                    "category_name": item.category.name if item.category else "Sin categoría",
                }
                for item in results
            ]

            logger.info(f"Search returned {len(data)} results for query: {query}")
            return data

    @staticmethod
    def get_search_suggestions(query: str, limit: int = 5) -> list[str]:
        """
        Get search suggestions based on query.

        Provides autocomplete-like functionality.
        """
        query_lower = query.lower().strip()
        query_lower.split()

        with get_session() as session:
            suggestions = []

            # Suggest category matches
            categories = (
                session.execute(
                    select(Category.name).where(Category.name.ilike(f"%{query_lower}%")).limit(3)
                )
                .scalars()
                .all()
            )
            for category in categories:
                suggestions.append({"type": "category", "value": category.name, "count": 1})

            # Suggest item name matches
            items = (
                session.execute(
                    select(MenuItem.name)
                    .where(MenuItem.name.ilike(f"%{query_lower}%"), MenuItem.is_available)
                    .limit(5)
                )
                .scalars()
                .all()
            )
            for item in items:
                suggestions.append({"type": "item", "value": item.name, "count": 1})

            logger.info(f"Generated {len(suggestions)} suggestions for query: {query}")
            return suggestions

    @staticmethod
    def get_popular_searches(days: int = 7, limit: int = 10) -> list[str]:
        """
        Get popular searches across all customers.

        Returns most frequently searched terms.
        """
        # For MVP, return hardcoded popular items
        popular_items = [
            "Café Americano",
            "Hamburguesa con queso",
            "Pizza Margarita",
            "Ensalada Caesar",
            "Tacos al pastor",
            "Papas fritas",
            "Limonesada",
            "Tarta de queso",
            "Helado",
            "Pollo al carbon",
            "Papas a la francesaEnsalada mixta",
            "Pastel de espinacas",
        ]

        return popular_items[:limit]
