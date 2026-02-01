from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.db import get_session
from shared.models import Secret

logger = logging.getLogger(__name__)

ENV_FILE_PATH = Path(__file__).resolve().parents[3] / "config" / "secrets.env"
SECRETS_ENV_ALLOWLIST_VAR = "SECRETS_ENV_ALLOWLIST"


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


def _update_env_value(key: str, value: str, path: Path = ENV_FILE_PATH) -> bool:
    lines = _load_env_lines(path)
    if not lines:
        return False

    env_map = _parse_env_lines(lines)
    if key not in env_map:
        return False

    allowlist = _get_allowlist(SECRETS_ENV_ALLOWLIST_VAR)
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


def load_env_secrets(path: Path = ENV_FILE_PATH) -> list[str]:
    lines = _load_env_lines(path)
    if not lines:
        return []
    env_map = _parse_env_lines(lines)
    allowlist = _get_allowlist(SECRETS_ENV_ALLOWLIST_VAR)
    if allowlist is not None:
        env_map = {key: value for key, value in env_map.items() if key in allowlist}
    for key, value in env_map.items():
        os.environ.setdefault(key, value)
    return list(env_map.keys())


def sync_env_secrets_to_db(path: Path = ENV_FILE_PATH) -> list[str]:
    lines = _load_env_lines(path)
    if not lines:
        return []

    env_map = _parse_env_lines(lines)
    allowlist = _get_allowlist(SECRETS_ENV_ALLOWLIST_VAR)
    if allowlist is not None:
        env_map = {key: value for key, value in env_map.items() if key in allowlist}
    if not env_map:
        return []

    inserted: list[str] = []
    with get_session() as session:
        existing = (
            session.execute(select(Secret).where(Secret.secret_key.in_(list(env_map.keys()))))
            .scalars()
            .all()
        )
        existing_keys = {secret.secret_key for secret in existing}

        for key, value in env_map.items():
            if key in existing_keys:
                continue
            session.add(Secret(secret_key=key, secret_value=value))
            inserted.append(key)

        if inserted:
            try:
                session.commit()
            except IntegrityError:
                # Race condition: another process inserted some keys concurrently
                session.rollback()
                logger.warning(
                    f"Race condition detected during secrets sync, some keys may have been skipped: {inserted}"
                )
                inserted = []

        secrets = (
            session.execute(select(Secret).where(Secret.secret_key.in_(list(env_map.keys()))))
            .scalars()
            .all()
        )
        for secret in secrets:
            os.environ[secret.secret_key] = secret.secret_value

    return inserted


def get_secret_value(key: str, default: str | None = None) -> str | None:
    with get_session() as session:
        secret = session.execute(select(Secret).where(Secret.secret_key == key)).scalars().first()
        if secret:
            return secret.secret_value

    env_map = _parse_env_lines(_load_env_lines())
    return env_map.get(key, default)


def set_secret_value(key: str, value: str) -> None:
    with get_session() as session:
        secret = session.execute(select(Secret).where(Secret.secret_key == key)).scalars().first()
        if secret:
            secret.secret_value = value
        else:
            session.add(Secret(secret_key=key, secret_value=value))
        session.commit()

    _update_env_value(key, value)
