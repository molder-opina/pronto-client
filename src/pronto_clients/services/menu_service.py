"""
Business logic around menu browsing for clients.
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from pronto_shared.db import get_session
from pronto_shared.models import (
    MenuCategory,
    MenuItem,
)
from pronto_shared.services.day_period_service import DayPeriodService


def _is_item_available_by_schedule(item: MenuItem) -> bool:
    """
    Check if item is available based on schedule.
    """
    if not item.is_available:
        return False

    if not item.schedules or len(item.schedules) == 0:
        return True

    current_time = datetime.utcnow().time()
    current_time_str = current_time.strftime("%H:%M")

    for schedule in item.schedules:
        start_time = schedule.start_time.strftime("%H:%M")
        end_time = schedule.end_time.strftime("%H:%M")

        if start_time <= current_time_str <= end_time:
            return True

    return False


def _get_current_period(periods: list) -> str:
    """
    Get current period based on time of day.
    """
    if not periods:
        return "morning"

    current_hour = datetime.utcnow().hour

    for period in periods:
        start_parts = period["start_time"].split(":")
        end_parts = period["end_time"].split(":")
        start_hour = int(start_parts[0])
        end_hour = int(end_parts[0])

        if start_hour <= current_hour < end_hour:
            return period["key"]

    return periods[0]["key"] if periods else "morning"


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
            if "debug" in category.name.lower() and not current_app.config.get("DEBUG", False):
                continue

            # Load items for this category
            items = (
                session.execute(
                    select(MenuItem)
                    .options(selectinload(MenuItem.modifier_groups))
                    .where(MenuItem.category_id == category.id)
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
                        (current_period == "breakfast" and item.is_breakfast_recommended)
                        or (current_period == "afternoon" and item.is_afternoon_recommended)
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
                        "modifier_groups": [
                            {
                                "id": mg.modifier_group.id,
                                "name": mg.modifier_group.name,
                                "description": mg.modifier_group.description,
                                "min_selection": mg.modifier_group.min_selection,
                                "max_selection": mg.modifier_group.max_selection,
                                "is_required": mg.modifier_group.is_required,
                                "display_order": mg.display_order,
                                "modifiers": [
                                    {
                                        "id": mod.id,
                                        "name": mod.name,
                                        "price_adjustment": float(mod.price_adjustment),
                                        "is_available": mod.is_available,
                                        "display_order": mod.display_order,
                                    }
                                    for mod in sorted(
                                        mg.modifier_group.modifiers, key=lambda m: m.display_order
                                    )
                                ],
                            }
                            for mg in sorted(item.modifier_groups, key=lambda x: x.display_order)
                        ],
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
                    select(MenuItem)
                    .options(selectinload(MenuItem.modifier_groups))
                    .where(MenuItem.category_id == category.id)
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
                        (current_period == "breakfast" and item.is_breakfast_recommended)
                        or (current_period == "afternoon" and item.is_afternoon_recommended)
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
