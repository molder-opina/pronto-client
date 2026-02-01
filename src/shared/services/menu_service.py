"""
Menu management helpers for employees.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from shared.db import get_session
from shared.models import MenuCategory, MenuItem, MenuItemDayPeriod, OrderItem
from shared.services.day_period_service import DayPeriodService
from shared.services.menu_validation import MenuValidator, MenuValidationError

logger = logging.getLogger(__name__)


def list_menu() -> dict:
    with get_session() as session:
        categories = (
            session.execute(
                select(MenuCategory)
                .options(
                    joinedload(MenuCategory.items)
                    .joinedload(MenuItem.day_period_assignments)
                    .joinedload(MenuItemDayPeriod.period)
                )
                .order_by(MenuCategory.display_order, MenuCategory.name)
            )
            .unique()
            .scalars()
            .all()
        )
        data = []
        for category in categories:
            data.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "items": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "description": item.description,
                            "price": float(item.price),
                            "is_available": item.is_available,
                            "is_quick_serve": item.is_quick_serve,
                            "preparation_time_minutes": item.preparation_time_minutes,
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
                        for item in category.items
                    ],
                }
            )
    return {"categories": data}


def _get_or_create_category(session, name: str) -> MenuCategory:
    stripped_name = name.strip()
    category = (
        session.execute(select(MenuCategory).where(MenuCategory.name == stripped_name))
        .scalars()
        .one_or_none()
    )
    if category is None:
        category = MenuCategory(name=stripped_name, display_order=99)
        try:
            session.add(category)
            session.flush()
        except IntegrityError:
            # Race condition: another request created the same category concurrently
            session.rollback()
            logger.warning(f"Race condition detected for category '{stripped_name}', re-querying")
            category = (
                session.execute(select(MenuCategory).where(MenuCategory.name == stripped_name))
                .scalars()
                .one_or_none()
            )
            if category is None:
                raise ValueError(f"Unable to create or recover category '{stripped_name}'")
    return category


def _parse_price(value: str | float | int) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("Precio inválido")


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _extract_recommendation_periods(payload: dict[str, Any]) -> list[str]:
    periods = payload.get("recommendation_periods")
    if isinstance(periods, list):
        return [str(key) for key in periods if key]
    keys: list[str] = []
    if _to_bool(payload.get("is_breakfast_recommended")):
        keys.append("breakfast")
    if _to_bool(payload.get("is_afternoon_recommended")):
        keys.append("afternoon")
    if _to_bool(payload.get("is_night_recommended")):
        keys.append("night")
    return keys


def create_menu_item(payload: dict[str, str]) -> tuple[dict, HTTPStatus]:
    with get_session() as session:
        try:
            # Validate payload
            validator = MenuValidator(session=session)
            validator.validate_create(payload)
        except MenuValidationError as exc:
            return {"error": str(exc)}, HTTPStatus.BAD_REQUEST

        category = _get_or_create_category(session, payload["category"])

        # Parse preparation time (default 15 if not provided)
        prep_time = 15
        if "preparation_time_minutes" in payload:
            try:
                prep_time = int(payload["preparation_time_minutes"])
                if prep_time < 0 or prep_time > 300:
                    prep_time = 15
            except (ValueError, TypeError):
                prep_time = 15

        item = MenuItem(
            name=payload["name"].strip(),
            description=payload.get("description"),
            price=_parse_price(payload["price"]),
            image_path=payload.get("image_path"),
            is_available=_to_bool(payload.get("is_available", True)),
            is_quick_serve=_to_bool(payload.get("is_quick_serve", False)),
            preparation_time_minutes=prep_time,
            category=category,
        )
        session.add(item)
        session.flush()

        DayPeriodService.update_item_periods(
            session, item, _extract_recommendation_periods(payload)
        )
        session.flush()

        return (
            {
                "id": item.id,
                "name": item.name,
                "price": float(item.price),
                "category": category.name,
                "recommendation_periods": [
                    assignment.period.period_key
                    for assignment in item.day_period_assignments
                    if assignment.tag_type == "recommendation" and assignment.period
                ],
            },
            HTTPStatus.CREATED,
        )


def update_menu_item(item_id: int, payload: dict[str, str]) -> tuple[dict, HTTPStatus]:
    with get_session() as session:
        try:
            # Validate payload
            validator = MenuValidator(session=session)
            validator.validate_update(item_id, payload)
        except MenuValidationError as exc:
            return {"error": str(exc)}, HTTPStatus.BAD_REQUEST

        item = session.get(MenuItem, item_id)
        if item is None:
            return {"error": "Producto no encontrado"}, HTTPStatus.NOT_FOUND

        if payload.get("name"):
            item.name = payload["name"].strip()
        if "description" in payload:
            item.description = payload["description"]
        if "price" in payload and payload["price"] is not None:
            try:
                item.price = _parse_price(payload["price"])
            except ValueError as exc:
                return {"error": str(exc)}, HTTPStatus.BAD_REQUEST
        if "image_path" in payload:
            item.image_path = payload["image_path"]
        if "is_available" in payload:
            item.is_available = _to_bool(payload["is_available"])
        if "is_quick_serve" in payload:
            item.is_quick_serve = _to_bool(payload["is_quick_serve"])
        if "preparation_time_minutes" in payload:
            try:
                prep_time = int(payload["preparation_time_minutes"])
                if 0 <= prep_time <= 300:
                    item.preparation_time_minutes = prep_time
            except (ValueError, TypeError):
                pass  # Keep existing value if invalid
        if payload.get("category"):
            item.category = _get_or_create_category(session, payload["category"])

        period_fields = {
            "recommendation_periods",
            "is_breakfast_recommended",
            "is_afternoon_recommended",
            "is_night_recommended",
        }
        if any(field in payload for field in period_fields):
            DayPeriodService.update_item_periods(
                session, item, _extract_recommendation_periods(payload)
            )

        session.add(item)

        return (
            {
                "id": item.id,
                "name": item.name,
                "price": float(item.price),
                "category": item.category.name,
                "is_available": item.is_available,
                "is_quick_serve": item.is_quick_serve,
                "recommendation_periods": [
                    assignment.period.period_key
                    for assignment in item.day_period_assignments
                    if assignment.tag_type == "recommendation" and assignment.period
                ],
            },
            HTTPStatus.OK,
        )


def delete_menu_item(item_id: int) -> tuple[dict, HTTPStatus]:
    with get_session() as session:
        try:
            # Validate deletion
            validator = MenuValidator(session=session)
            validator.validate_delete(item_id)
        except MenuValidationError as exc:
            return {"error": str(exc)}, HTTPStatus.CONFLICT

        item = session.get(MenuItem, item_id)
        if item is None:
            return {"error": "Producto no encontrado"}, HTTPStatus.NOT_FOUND

        session.delete(item)
        return {"deleted": item_id}, HTTPStatus.OK
