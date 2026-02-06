"""
Business logic around menu browsing for clients.
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app
from sqlalchemy import select

from pronto_shared.db import get_session
from pronto_shared.models import (
    MenuCategory,
    MenuItem,
    ModifierGroup,
    Modifier,
)
from pronto_shared.services.day_period_service import DayPeriodService


def _is_item_available_by_schedule(item: MenuItem) -> bool:
    """
    Check if item is available based on schedule.
    Note: Schedule-based availability is temporarily disabled due to schema mismatch.
    """
    if not item.is_available:
        return False
    return True


def _get_current_period(periods: list) -> str:
    """
    Get current period based on time of day.
    """
    if not periods:
        return "morning"

    current_hour = datetime.utcnow().hour

    for period in periods:
        start_time = period["start_time"]
        end_time = period["end_time"]

        # Handle both string and datetime.time objects
        if hasattr(start_time, "hour"):
            start_hour = start_time.hour
        else:
            start_hour = int(start_time.split(":")[0])

        if hasattr(end_time, "hour"):
            end_hour = end_time.hour
        else:
            end_hour = int(end_time.split(":")[0])

        if start_hour <= current_hour < end_hour:
            return period["key"]

    return periods[0]["key"] if periods else "morning"


def _get_modifier_groups_for_item(session, item_id: str) -> list:
    """
    Get modifier groups for a menu item using direct query.
    Uses the actual DB schema where modifier_groups has menu_item_id column.
    """
    from sqlalchemy import text

    query = text("""
        SELECT mg.id, mg.name, mg.description, mg.min_selections,
               mg.max_selections, mg.is_required
        FROM pronto_modifier_groups mg
        WHERE mg.menu_item_id = :item_id
    """)

    result = session.execute(query, {"item_id": item_id}).fetchall()

    groups = []
    for row in result:
        modifiers_query = text("""
            SELECT id, name, price_adjustment, is_available
            FROM pronto_modifiers
            WHERE group_id = :group_id
        """)
        modifiers = session.execute(
            modifiers_query, {"group_id": str(row.id)}
        ).fetchall()

        groups.append(
            {
                "id": str(row.id),
                "name": row.name,
                "description": row.description,
                "min_selection": row.min_selections,
                "max_selection": row.max_selections,
                "is_required": row.is_required,
                "display_order": 0,
                "modifiers": [
                    {
                        "id": str(mod.id),
                        "name": mod.name,
                        "price_adjustment": float(mod.price_adjustment)
                        if mod.price_adjustment
                        else 0,
                        "is_available": mod.is_available,
                        "display_order": 0,
                    }
                    for mod in modifiers
                ],
            }
        )

    return groups


def fetch_menu() -> dict:
    """
    Retrieve menu categories and items formatted for JSON responses.
    """
    with get_session() as session:
        # Load categories first
        categories = (
            session.execute(select(MenuCategory).order_by(MenuCategory.display_order))
            .scalars()
            .all()
        )

        # Load periods
        periods = DayPeriodService.list_periods(session=session)
        current_period = _get_current_period(periods)
        period_label_map = {period["key"]: period["name"] for period in periods}

        # Load items separately to avoid complex relationship loading
        payload = []
        for category in categories:
            # Skip Debug category in production
            if "debug" in category.name.lower() and not current_app.config.get(
                "DEBUG", False
            ):
                continue

            # Load items for this category
            items = (
                session.execute(
                    select(MenuItem).where(MenuItem.category_id == category.id)
                )
                .scalars()
                .all()
            )

            items_data = []
            for item in items:
                # Check schedule availability
                available_by_schedule = _is_item_available_by_schedule(item)
                # Item is available if both flags are True
                final_availability = item.is_available and available_by_schedule

                # Check if item is recommended for current period
                is_recommended = False
                if current_period in ["breakfast", "afternoon", "night"]:
                    if (
                        (
                            current_period == "breakfast"
                            and item.is_breakfast_recommended
                        )
                        or (
                            current_period == "afternoon"
                            and item.is_afternoon_recommended
                        )
                        or (current_period == "night" and item.is_night_recommended)
                    ):
                        is_recommended = True

                items_data.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "price": float(item.price),
                        "is_available": final_availability,
                        "available_by_schedule": available_by_schedule,
                        "image_path": item.image_path,
                        "preparation_time_minutes": item.preparation_time_minutes or 15,
                        "is_quick_serve": item.is_quick_serve,
                        "is_breakfast_recommended": is_recommended,
                        "is_afternoon_recommended": is_recommended,
                        "is_night_recommended": is_recommended,
                        "recommendation_periods": [],
                        "modifier_groups": _get_modifier_groups_for_item(
                            session, str(item.id)
                        ),
                    }
                )

            payload.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "description": category.description,
                    "items": items_data,
                }
            )

        # Get recommended items for current period
        all_items = []
        for category in categories:
            # Load items for this category
            items = (
                session.execute(
                    select(MenuItem).where(MenuItem.category_id == category.id)
                )
                .scalars()
                .all()
            )

            for item in items:
                available_by_schedule = _is_item_available_by_schedule(item)
                final_availability = item.is_available and available_by_schedule

                # Only include available items
                if not final_availability:
                    continue

                is_recommended = False
                if current_period in ["breakfast", "afternoon", "night"]:
                    if (
                        (
                            current_period == "breakfast"
                            and item.is_breakfast_recommended
                        )
                        or (
                            current_period == "afternoon"
                            and item.is_afternoon_recommended
                        )
                        or (current_period == "night" and item.is_night_recommended)
                    ):
                        is_recommended = True

                all_items.append(item)

        return {
            "categories": payload,
            "periods": periods,
            "recommended": {
                "period": current_period,
                "period_label": period_label_map.get(current_period, "Recomendados"),
                "items": [{"id": item.id} for item in all_items],
            },
        }
