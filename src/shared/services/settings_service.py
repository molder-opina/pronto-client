"""Service for managing system-wide settings."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from shared.db import get_session
from shared.models import SystemSetting


class SettingsService:
    """Service for managing system settings."""

    DEFAULT_SETTINGS = {
        "show_estimated_time": {
            "value": "true",
            "value_type": "bool",
            "description": "Mostrar tiempo estimado de preparación en resumen de pedidos",
            "category": "orders",
        },
        "estimated_time_min": {
            "value": "25",
            "value_type": "int",
            "description": "Tiempo estimado mínimo de preparación (minutos)",
            "category": "orders",
        },
        "estimated_time_max": {
            "value": "30",
            "value_type": "int",
            "description": "Tiempo estimado máximo de preparación (minutos)",
            "category": "orders",
        },
        "order_status_labels": {
            "value": json.dumps(
                {
                    "new": "Orden creada",
                    "queued": "En cola",
                    "preparing": "Cocinando",
                    "ready": "Listo para entregar",
                    "delivered": "Entregado",
                    "awaiting_payment": "Pendiente de pago",
                    "paid": "Pagado",
                    "cancelled": "Cancelado",
                }
            ),
            "value_type": "json",
            "description": "Alias visibles para los estados de orden/sesión en apps de clientes y empleados",
            "category": "orders",
        },
        "paid_orders_window_minutes": {
            "value": "60",
            "value_type": "int",
            "description": "Minutos que las órdenes pagadas permanecen visibles en activos antes de ocultarse",
            "category": "orders",
        },
        "table_base_prefix": {
            "value": "M",
            "value_type": "string",
            "description": "Prefijo base para numerar mesas (antes del número). Ej. M → M01, V-M01.",
            "category": "orders",
        },
        "waiter_notification_sound": {
            "value": "bell",
            "value_type": "string",
            "description": "Tipo de sonido de notificación para nuevas órdenes en panel de mesero. Opciones: bell (campanita), chime (carillón), beep (bip), ding (timbre), pop (pop suave)",
            "category": "orders",
        },
        "waiter_notification_timeout": {
            "value": "3000",
            "value_type": "int",
            "description": "Tiempo en milisegundos que permanecen visibles las notificaciones de mesero antes de cerrarse automáticamente",
            "category": "orders",
        },
        "system_role_permissions": {
            "value": json.dumps(
                {
                    "super_admin": [
                        "waiter-board",
                        "kitchen-board",
                        "payments-process",
                        "menu-manage",
                    ],
                    "admin_roles": [
                        "waiter-board",
                        "kitchen-board",
                        "payments-process",
                        "menu-manage",
                    ],
                    "waiter": ["waiter-board"],
                    "chef": ["kitchen-board"],
                    "cashier": ["payments-process"],
                    "content_manager": ["menu-manage"],
                }
            ),
            "value_type": "json",
            "description": "Mapa de permisos por rol para el módulo de Roles y Permisos del sistema",
            "category": "security",
        },
        "areas_list": {
            "value": json.dumps([]),
            "value_type": "json",
            "description": "Lista de areas/salones configuradas para mesas",
            "category": "general",
        },
    }

    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        """Get a setting value by key, returns typed value."""
        try:
            with get_session() as session:
                setting = (
                    session.execute(select(SystemSetting).where(SystemSetting.key == key))
                    .scalars()
                    .first()
                )

                if setting:
                    return setting.get_typed_value()
        except Exception as e:
            # Fallback to defaults if DB fails (prevents app crash)
            import logging

            logging.getLogger(__name__).error(f"Error fetching setting {key}: {e}")

        # Return default from DEFAULT_SETTINGS if available
        if key in SettingsService.DEFAULT_SETTINGS:
            return SettingsService._parse_value(
                SettingsService.DEFAULT_SETTINGS[key]["value"],
                SettingsService.DEFAULT_SETTINGS[key]["value_type"],
            )

        return default

    @staticmethod
    def set_setting(key: str, value: Any, employee_id: int | None = None) -> dict[str, Any]:
        """Set a setting value."""
        with get_session() as session:
            setting = (
                session.execute(select(SystemSetting).where(SystemSetting.key == key))
                .scalars()
                .one_or_none()
            )

            # Convert value to string for storage
            if isinstance(value, (dict, list)):
                import json

                str_value = json.dumps(value)
            elif isinstance(value, bool):
                str_value = str(value).lower()
            else:
                str_value = str(value)

            if setting:
                setting.value = str_value
                setting.updated_by = employee_id
            else:
                # Get default config if exists
                default_config = SettingsService.DEFAULT_SETTINGS.get(key, {})
                setting = SystemSetting(
                    key=key,
                    value=str_value,
                    value_type=default_config.get("value_type", "string"),
                    description=default_config.get("description"),
                    category=default_config.get("category", "general"),
                    updated_by=employee_id,
                )
                session.add(setting)

            session.flush()
            session.refresh(setting)

            return {
                "key": setting.key,
                "value": setting.get_typed_value(),
                "value_type": setting.value_type,
                "description": setting.description,
                "category": setting.category,
            }

    @staticmethod
    def get_all_settings(category: str | None = None) -> list[dict[str, Any]]:
        """Get all settings, optionally filtered by category."""
        with get_session() as session:
            query = select(SystemSetting)
            if category:
                query = query.where(SystemSetting.category == category)

            settings = (
                session.execute(query.order_by(SystemSetting.category, SystemSetting.key))
                .scalars()
                .all()
            )

            result = []
            for setting in settings:
                result.append(
                    {
                        "id": setting.id,
                        "key": setting.key,
                        "value": setting.get_typed_value(),
                        "raw_value": setting.value,
                        "value_type": setting.value_type,
                        "description": setting.description,
                        "category": setting.category,
                        "updated_at": setting.updated_at.isoformat()
                        if setting.updated_at
                        else None,
                    }
                )

            # Add default settings that aren't in the database yet
            existing_keys = {s["key"] for s in result}
            for key, config in SettingsService.DEFAULT_SETTINGS.items():
                if key not in existing_keys:
                    result.append(
                        {
                            "id": None,
                            "key": key,
                            "value": SettingsService._parse_value(
                                config["value"], config["value_type"]
                            ),
                            "raw_value": config["value"],
                            "value_type": config["value_type"],
                            "description": config.get("description"),
                            "category": config.get("category", "general"),
                            "updated_at": None,
                        }
                    )

            # Filter by category if specified
            if category:
                result = [s for s in result if s["category"] == category]

            return sorted(result, key=lambda x: (x["category"], x["key"]))

    @staticmethod
    def initialize_defaults() -> None:
        """Initialize default settings in the database."""
        with get_session() as session:
            for key, config in SettingsService.DEFAULT_SETTINGS.items():
                existing = (
                    session.execute(select(SystemSetting).where(SystemSetting.key == key))
                    .scalars()
                    .one_or_none()
                )

                if not existing:
                    setting = SystemSetting(
                        key=key,
                        value=config["value"],
                        value_type=config["value_type"],
                        description=config.get("description"),
                        category=config.get("category", "general"),
                    )
                    session.add(setting)

            session.flush()

    @staticmethod
    def _parse_value(value: str, value_type: str) -> Any:
        """Parse a string value to its proper type."""
        if value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "json":
            import json

            return json.loads(value)
        return value


def get_setting(key: str, default: Any = None) -> Any:
    """Convenience function to get a setting."""
    return SettingsService.get_setting(key, default)


def set_setting(key: str, value: Any, employee_id: int | None = None) -> dict[str, Any]:
    """Convenience function to set a setting."""
    return SettingsService.set_setting(key, value, employee_id)
