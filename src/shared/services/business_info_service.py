"""Service for managing business information and schedule."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select

from shared.db import get_session
from shared.models import BusinessInfo, BusinessSchedule, Employee
from shared.services.business_config_service import get_config_value, set_config_value

logger = logging.getLogger(__name__)


class BusinessInfoService:
    """Service for managing business information."""

    ENV_FILE_PATH = Path(__file__).resolve().parents[3] / "config" / "general.env"

    @staticmethod
    def _get_restaurant_name_from_env() -> str | None:
        """Read RESTAURANT_NAME from general.env file."""
        try:
            if not BusinessInfoService.ENV_FILE_PATH.exists():
                return None

            with open(BusinessInfoService.ENV_FILE_PATH) as f:
                content = f.read()
                match = re.search(r"^RESTAURANT_NAME=(.+)$", content, re.MULTILINE)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            logger.warning(f"Error reading RESTAURANT_NAME from env: {e}")
        return None

    @staticmethod
    def _update_restaurant_name_in_env(new_name: str) -> bool:
        """Update RESTAURANT_NAME in general.env file."""
        try:
            if not BusinessInfoService.ENV_FILE_PATH.exists():
                return False

            with open(BusinessInfoService.ENV_FILE_PATH) as f:
                content = f.read()

            # Replace RESTAURANT_NAME value
            updated_content = re.sub(
                r"^RESTAURANT_NAME=.+$", f"RESTAURANT_NAME={new_name}", content, flags=re.MULTILINE
            )

            with open(BusinessInfoService.ENV_FILE_PATH, "w") as f:
                f.write(updated_content)

            return True
        except Exception as e:
            logger.warning(f"Error updating RESTAURANT_NAME in env: {e}")
            return False

    @staticmethod
    def get_business_info() -> dict[str, Any] | None:
        """Get business information (singleton)."""
        with get_session() as session:
            info = session.execute(select(BusinessInfo).limit(1)).scalars().first()

            # If no info in database, get restaurant name from env
            if not info:
                env_name = BusinessInfoService._get_restaurant_name_from_env()
                if env_name:
                    return {
                        "business_name": env_name,
                        "currency": "MXN",
                        "timezone": "America/Mexico_City",
                    }
                return None

            return {
                "id": info.id,
                "business_name": info.business_name,
                "address": info.address,
                "city": info.city,
                "state": info.state,
                "postal_code": info.postal_code,
                "country": info.country,
                "phone": info.phone,
                "email": info.email,
                "website": info.website,
                "logo_url": info.logo_url,
                "description": info.description,
                "currency": info.currency,
                "timezone": info.timezone,
                "updated_at": info.updated_at.isoformat() if info.updated_at else None,
                "waiter_call_sound": get_config_value("waiter_call_sound", "bell1.mp3"),
            }

    @staticmethod
    def create_or_update_business_info(
        data: dict[str, Any], employee_id: int | None = None
    ) -> dict[str, Any]:
        """Create or update business information."""
        with get_session() as session:
            updater_id = BusinessInfoService._resolve_updater_id(session, employee_id)
            info = session.execute(select(BusinessInfo).limit(1)).scalars().first()

            # Check if business_name is being updated
            business_name_changed = False
            new_business_name = data.get("business_name")

            waiter_call_sound = data.pop("waiter_call_sound", None)

            if info:
                # Update existing
                if new_business_name and info.business_name != new_business_name:
                    business_name_changed = True

                for key, value in data.items():
                    if hasattr(info, key):
                        setattr(info, key, value)
                info.updated_by = updater_id
            else:
                # Create new
                if new_business_name:
                    business_name_changed = True
                info = BusinessInfo(**data, updated_by=updater_id)
                session.add(info)

            session.flush()
            session.refresh(info)

            if waiter_call_sound:
                set_config_value(
                    key="waiter_call_sound",
                    value=waiter_call_sound,
                    value_type="string",
                    category="general",
                    display_name="Sonido de Campana",
                    description="Archivo de sonido para la llamada al mesero",
                    employee_id=employee_id,
                )

            # Update general.env if business name changed
            if business_name_changed and info.business_name:
                BusinessInfoService._update_restaurant_name_in_env(info.business_name)

            return {
                "id": info.id,
                "business_name": info.business_name,
                "address": info.address,
                "city": info.city,
                "state": info.state,
                "postal_code": info.postal_code,
                "country": info.country,
                "phone": info.phone,
                "email": info.email,
                "website": info.website,
                "logo_url": info.logo_url,
                "description": info.description,
                "currency": info.currency,
                "timezone": info.timezone,
                "updated_at": info.updated_at.isoformat() if info.updated_at else None,
                "waiter_call_sound": waiter_call_sound
                or get_config_value("waiter_call_sound", "bell1.mp3"),
            }

    @staticmethod
    def _resolve_updater_id(session, employee_id: int | None) -> int | None:
        """Return a valid employee id if it exists to honor FK constraints."""
        if not employee_id:
            return None
        employee = session.get(Employee, employee_id)
        return employee.id if employee else None


class BusinessScheduleService:
    """Service for managing business schedule."""

    DAYS_OF_WEEK = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo",
    }

    @staticmethod
    def get_schedule() -> list[dict[str, Any]]:
        """Get complete business schedule for all days."""
        with get_session() as session:
            schedules = (
                session.execute(select(BusinessSchedule).order_by(BusinessSchedule.day_of_week))
                .scalars()
                .all()
            )

            result = []
            existing_days = {s.day_of_week: s for s in schedules}

            # Ensure all 7 days are represented
            for day in range(7):
                if day in existing_days:
                    s = existing_days[day]
                    result.append(
                        {
                            "id": s.id,
                            "day_of_week": s.day_of_week,
                            "day_name": BusinessScheduleService.DAYS_OF_WEEK[s.day_of_week],
                            "is_open": s.is_open,
                            "open_time": s.open_time,
                            "close_time": s.close_time,
                            "notes": s.notes,
                        }
                    )
                else:
                    # Default to open 9:00-22:00
                    result.append(
                        {
                            "id": None,
                            "day_of_week": day,
                            "day_name": BusinessScheduleService.DAYS_OF_WEEK[day],
                            "is_open": True,
                            "open_time": "09:00",
                            "close_time": "22:00",
                            "notes": None,
                        }
                    )

            return result

    @staticmethod
    def get_schedule_for_day(day_of_week: int) -> dict[str, Any] | None:
        """Get schedule for a specific day."""
        if day_of_week < 0 or day_of_week > 6:
            raise ValueError("day_of_week must be between 0 and 6")

        with get_session() as session:
            schedule = (
                session.execute(
                    select(BusinessSchedule).where(BusinessSchedule.day_of_week == day_of_week)
                )
                .scalars()
                .first()
            )

            if not schedule:
                return {
                    "id": None,
                    "day_of_week": day_of_week,
                    "day_name": BusinessScheduleService.DAYS_OF_WEEK[day_of_week],
                    "is_open": True,
                    "open_time": "09:00",
                    "close_time": "22:00",
                    "notes": None,
                }

            return {
                "id": schedule.id,
                "day_of_week": schedule.day_of_week,
                "day_name": BusinessScheduleService.DAYS_OF_WEEK[schedule.day_of_week],
                "is_open": schedule.is_open,
                "open_time": schedule.open_time,
                "close_time": schedule.close_time,
                "notes": schedule.notes,
            }

    @staticmethod
    def update_schedule(day_of_week: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update schedule for a specific day."""
        if day_of_week < 0 or day_of_week > 6:
            raise ValueError("day_of_week must be between 0 and 6")

        with get_session() as session:
            schedule = (
                session.execute(
                    select(BusinessSchedule).where(BusinessSchedule.day_of_week == day_of_week)
                )
                .scalars()
                .first()
            )

            if schedule:
                # Update existing
                for key, value in data.items():
                    if hasattr(schedule, key) and key != "day_of_week":
                        setattr(schedule, key, value)
            else:
                # Create new
                schedule = BusinessSchedule(day_of_week=day_of_week, **data)
                session.add(schedule)

            session.flush()
            session.refresh(schedule)

            return {
                "id": schedule.id,
                "day_of_week": schedule.day_of_week,
                "day_name": BusinessScheduleService.DAYS_OF_WEEK[schedule.day_of_week],
                "is_open": schedule.is_open,
                "open_time": schedule.open_time,
                "close_time": schedule.close_time,
                "notes": schedule.notes,
            }

    @staticmethod
    def bulk_update_schedule(schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Update multiple days at once."""
        result = []
        for schedule_data in schedules:
            day = schedule_data.pop("day_of_week")
            updated = BusinessScheduleService.update_schedule(day, schedule_data)
            result.append(updated)
        return result
