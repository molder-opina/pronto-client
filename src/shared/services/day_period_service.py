"""Service utilities for configurable day periods used across the platform."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import DayPeriod, MenuItem, MenuItemDayPeriod

logger = get_logger(__name__)

DEFAULT_PERIODS = [
    {
        "period_key": "breakfast",
        "name": "Mañana",
        "icon": "☕",
        "color": "#f97316",
        "start_time": "06:00",
        "end_time": "12:00",
        "display_order": 1,
        "is_default": True,
    },
    {
        "period_key": "afternoon",
        "name": "Tarde",
        "icon": "🌮",
        "color": "#0ea5e9",
        "start_time": "12:00",
        "end_time": "18:00",
        "display_order": 2,
        "is_default": True,
    },
    {
        "period_key": "night",
        "name": "Noche",
        "icon": "🌙",
        "color": "#6366f1",
        "start_time": "18:00",
        "end_time": "06:00",
        "display_order": 3,
        "is_default": True,
    },
]


class DayPeriodService:
    """CRUD helpers for day periods and menu-item associations."""

    @staticmethod
    def list_periods(session: Session | None = None) -> list[dict[str, Any]]:
        """
        Return configured day periods, optionally reusing an existing session to
        avoid detaching parent objects mid-transaction.
        """
        if session is None:
            with get_session() as scoped_session:
                return DayPeriodService._list_periods_with_session(scoped_session)
        return DayPeriodService._list_periods_with_session(session)

    @staticmethod
    def _list_periods_with_session(session: Session) -> list[dict[str, Any]]:
        periods = DayPeriodService._query_periods(session)
        if not periods:
            DayPeriodService._ensure_defaults(session)
            periods = DayPeriodService._query_periods(session)
        return [DayPeriodService._serialize(period) for period in periods]

    @staticmethod
    def _query_periods(session: Session) -> list[DayPeriod]:
        return (
            session.execute(
                select(DayPeriod).order_by(DayPeriod.display_order, DayPeriod.start_time)
            )
            .unique()
            .scalars()
            .all()
        )

    @staticmethod
    def get_period_map(session=None) -> dict[str, DayPeriod]:
        """Return dictionary keyed by period_key."""
        if session is None:
            with get_session() as scoped_session:
                return DayPeriodService.get_period_map(session=scoped_session)

        periods = (
            session.execute(
                select(DayPeriod).order_by(DayPeriod.display_order, DayPeriod.start_time)
            )
            .unique()
            .scalars()
            .all()
        )
        return {period.period_key: period for period in periods}

    @staticmethod
    def create_period(data: dict[str, Any]) -> dict[str, Any]:
        DayPeriodService._validate_period_payload(data)

        with get_session() as session:
            period = DayPeriod(
                period_key=data["period_key"],
                name=data["name"],
                description=data.get("description"),
                icon=data.get("icon"),
                color=data.get("color"),
                start_time=data["start_time"],
                end_time=data["end_time"],
                display_order=data.get("display_order", 0),
                is_default=bool(data.get("is_default", False)),
            )
            session.add(period)
            session.flush()
            session.refresh(period)
            return DayPeriodService._serialize(period)

    @staticmethod
    def update_period(period_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data:
            return None

        if "start_time" in data or "end_time" in data:
            DayPeriodService._validate_period_payload(data, partial=True)

        with get_session() as session:
            period = session.get(DayPeriod, period_id)
            if not period:
                return None

            for field in [
                "period_key",
                "name",
                "description",
                "icon",
                "color",
                "start_time",
                "end_time",
                "display_order",
                "is_default",
            ]:
                if field in data and data[field] is not None:
                    setattr(period, field, data[field])

            session.add(period)
            session.flush()
            session.refresh(period)
            return DayPeriodService._serialize(period)

    @staticmethod
    def delete_period(period_id: int) -> bool:
        with get_session() as session:
            period = session.get(DayPeriod, period_id)
            if not period:
                return False
            session.delete(period)
            session.flush()
            return True

    @staticmethod
    def update_item_periods(
        session,
        menu_item: MenuItem,
        period_keys: Sequence[str] | None,
        tag_type: str = "recommendation",
    ) -> None:
        """Attach menu_item to the provided period keys, removing previous assignments."""
        if period_keys is None:
            period_keys = []

        desired_keys: set[str] = {key for key in period_keys if key}
        if not hasattr(menu_item, "day_period_assignments"):
            menu_item.day_period_assignments = []

        # Remove assignments not in desired set
        for assignment in list(menu_item.day_period_assignments):
            if assignment.tag_type != tag_type:
                continue
            if not assignment.period or assignment.period.period_key not in desired_keys:
                session.delete(assignment)

        if desired_keys:
            period_map = DayPeriodService.get_period_map(session=session)
            for key in desired_keys:
                period = period_map.get(key)
                if not period:
                    continue
                already_linked = any(
                    ap.period and ap.period.period_key == key and ap.tag_type == tag_type
                    for ap in menu_item.day_period_assignments
                )
                if not already_linked:
                    menu_item.day_period_assignments.append(
                        MenuItemDayPeriod(period=period, tag_type=tag_type)
                    )

        DayPeriodService._sync_legacy_flags(menu_item, desired_keys)

    @staticmethod
    def _sync_legacy_flags(menu_item: MenuItem, period_keys: Iterable[str]) -> None:
        """Keep legacy boolean columns updated for backwards compatibility."""
        keys = set(period_keys or [])
        menu_item.is_breakfast_recommended = "breakfast" in keys
        menu_item.is_afternoon_recommended = "afternoon" in keys
        menu_item.is_night_recommended = "night" in keys

    @staticmethod
    def _validate_period_payload(data: dict[str, Any], partial: bool = False) -> None:
        required_fields = ["period_key", "name", "start_time", "end_time"]
        if not partial:
            missing = [field for field in required_fields if not data.get(field)]
            if missing:
                raise ValueError(f"Campos requeridos faltantes: {', '.join(missing)}")

        for time_field in ["start_time", "end_time"]:
            if data.get(time_field):
                DayPeriodService._validate_time(data[time_field])

    @staticmethod
    def _validate_time(value: str) -> None:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            raise ValueError("El formato de hora debe ser HH:MM")

    @staticmethod
    def _serialize(period: DayPeriod) -> dict[str, Any]:
        return {
            "id": period.id,
            "key": period.period_key,
            "name": period.name,
            "description": period.description,
            "icon": period.icon,
            "color": period.color,
            "start_time": period.start_time,
            "end_time": period.end_time,
            "display_order": period.display_order,
            "is_default": period.is_default,
        }

    @staticmethod
    def _ensure_defaults(session) -> None:
        """Ensure the default records exist."""
        existing = {
            period.period_key for period in session.execute(select(DayPeriod)).scalars().all()
        }
        for config in DEFAULT_PERIODS:
            if config["period_key"] not in existing:
                period = DayPeriod(**config)
                session.add(period)
        session.flush()
