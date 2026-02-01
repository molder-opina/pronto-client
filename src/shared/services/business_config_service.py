"""Utilities to access BusinessConfig values."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.db import get_session
from shared.models import BusinessConfig

logger = logging.getLogger(__name__)

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / "config" / "general.env"
GENERAL_ENV_ALLOWLIST_VAR = "GENERAL_ENV_ALLOWLIST"


def _load_env_lines(path: Path = ENV_FILE_PATH) -> list[str]:
    try:
        if not path.exists():
            return []
        return path.read_text().splitlines(keepends=True)
    except OSError:
        return []


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_env_lines(lines: list[str]) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env_map[key.strip()] = _strip_quotes(value.strip())
    return env_map


def _get_allowlist(env_var: str) -> set[str] | None:
    raw = os.getenv(env_var)
    if not raw:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def _detect_value_type(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        return "bool"
    try:
        int(value)
        return "int"
    except (TypeError, ValueError):
        pass
    try:
        float(value)
        return "float"
    except (TypeError, ValueError):
        pass
    if value.strip().startswith("{") or value.strip().startswith("["):
        return "json"
    return "string"


def _coerce_env_value(value: str) -> Any:
    value_type = _detect_value_type(value)
    if value_type == "bool":
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if value_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if value_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if value_type == "json":
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _update_env_value(key: str, value: str, path: Path = ENV_FILE_PATH) -> bool:
    lines = _load_env_lines(path)
    if not lines:
        return False

    env_map = _parse_env_lines(lines)
    if key not in env_map:
        return False

    allowlist = _get_allowlist(GENERAL_ENV_ALLOWLIST_VAR)
    if allowlist is not None and key not in allowlist:
        return False

    pattern = re.compile(rf"^(export\s+)?{re.escape(key)}=", re.MULTILINE)
    updated = False
    for idx, line in enumerate(lines):
        if pattern.match(line):
            prefix = "export " if line.lstrip().startswith("export ") else ""
            lines[idx] = f"{prefix}{key}={value}{os.linesep}"
            updated = True
            break
    if not updated:
        return False
    try:
        path.write_text("".join(lines))
        return True
    except OSError:
        return False


def sync_env_config_to_db(
    keys: Iterable[str] | None = None, path: Path = ENV_FILE_PATH
) -> list[str]:
    lines = _load_env_lines(path)
    if not lines:
        return []
    env_map = _parse_env_lines(lines)
    allowlist = _get_allowlist(GENERAL_ENV_ALLOWLIST_VAR)
    if keys is not None:
        allowed = set(keys)
        env_map = {key: value for key, value in env_map.items() if key in allowed}
    elif allowlist is not None:
        env_map = {key: value for key, value in env_map.items() if key in allowlist}
    if not env_map:
        return []

    inserted: list[str] = []
    with get_session() as session:
        existing = (
            session.execute(
                select(BusinessConfig).where(BusinessConfig.config_key.in_(list(env_map.keys())))
            )
            .scalars()
            .all()
        )
        existing_keys = {config.config_key for config in existing}

        for key, value in env_map.items():
            if key in existing_keys:
                continue
            value_type = _detect_value_type(value)
            config = BusinessConfig(
                config_key=key,
                config_value=value,
                value_type=value_type,
                category="general",
                display_name=key,
                description="Synced from general.env",
            )
            session.add(config)
            inserted.append(key)

        if inserted:
            try:
                session.commit()
            except IntegrityError:
                # Race condition: another process inserted some keys concurrently
                session.rollback()
                logger.warning(
                    f"Race condition detected during config sync, some keys may have been skipped: {inserted}"
                )
                # Re-sync to ensure all keys are present
                inserted = []

    return inserted


def _parse_value(config: BusinessConfig) -> Any:
    value = config.config_value
    value_type = (config.value_type or "string").lower()
    if value is None:
        return None
    if value_type == "int":
        try:
            return int(value)
        except ValueError:
            return value
    if value_type == "float":
        try:
            return float(value)
        except ValueError:
            return value
    if value_type == "bool":
        return str(value).lower() in {"true", "1", "yes"}
    if value_type == "json":
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def get_config_map(keys: Iterable[str]) -> dict[str, Any]:
    """Return a dict with the requested config keys parsed to their value type."""
    keys = list(keys)
    if not keys:
        return {}

    with get_session() as session:
        configs = (
            session.execute(select(BusinessConfig).where(BusinessConfig.config_key.in_(keys)))
            .scalars()
            .all()
        )
        parsed = {config.config_key: _parse_value(config) for config in configs}

    if len(parsed) != len(keys):
        env_map = _parse_env_lines(_load_env_lines())
        allowlist = _get_allowlist(GENERAL_ENV_ALLOWLIST_VAR)
        for key in keys:
            if key not in parsed and key in env_map:
                if allowlist is not None and key not in allowlist:
                    continue
                parsed[key] = _coerce_env_value(env_map[key])

    return parsed


def get_config_value(key: str, default: Any = None) -> Any:
    """Return a single config value or default if not found."""
    result = get_config_map([key])
    return result.get(key, default)


class ConfigService:
    """Simple config accessor backed by BusinessConfig."""

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = get_config_value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def get_int(self, key: str, default: int = 0) -> int:
        value = get_config_value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_string(self, key: str, default: str = "") -> str:
        value = get_config_value(key, default)
        return str(value) if value is not None else default


def set_config_value(
    key: str,
    value: Any,
    value_type: str = "string",
    category: str = "general",
    display_name: str | None = None,
    description: str | None = None,
    employee_id: int | None = None,
) -> None:
    """Set a configuration value."""
    with get_session() as session:
        config = (
            session.execute(select(BusinessConfig).where(BusinessConfig.config_key == key))
            .scalars()
            .first()
        )

        str_value = str(value)
        if value_type == "json" and not isinstance(value, str):
            str_value = json.dumps(value)

        if config:
            config.config_value = str_value
            config.value_type = value_type
            if category:
                config.category = category
            if display_name:
                config.display_name = display_name
            if description:
                config.description = description
            config.updated_by = employee_id
        else:
            config = BusinessConfig(
                config_key=key,
                config_value=str_value,
                value_type=value_type,
                category=category,
                display_name=display_name or key,
                description=description,
                updated_by=employee_id,
            )
            session.add(config)
        session.commit()

    _update_env_value(key, str_value)
