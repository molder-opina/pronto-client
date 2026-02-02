"""Utility helpers to sanitize and normalize client inputs."""

from __future__ import annotations

import re
import unicodedata


class InputValidationError(ValueError):
    """Raised when a user supplied value contains forbidden content."""


SAFE_NAME_PATTERN = re.compile(r"^[A-Z0-9\s\-\.'&,]+$")
SAFE_NOTE_PATTERN = re.compile(r"^[A-Z0-9\s\-\.,#@!:/()&]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9\s\-]{5,20}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
SUPPORT_PATTERN = re.compile(r"^[A-Z0-9\s\-\.,;:!?#@/()&\"'_\[\]]+$")


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _reject_html(value: str, field: str) -> None:
    if "<" in value or ">" in value:
        raise InputValidationError(f"Caracteres no permitidos en {field}")


def sanitize_customer_name(value: str | None, allow_empty: bool = False, default: str = "") -> str:
    if not value:
        if allow_empty:
            return default
        raise InputValidationError("El nombre es requerido")

    cleaned = _strip_accents(value).strip().upper()
    _reject_html(cleaned, "nombre")

    if not SAFE_NAME_PATTERN.fullmatch(cleaned):
        raise InputValidationError("El nombre contiene caracteres no permitidos")

    return cleaned


def sanitize_phone(value: str | None) -> str:
    if not value:
        return ""

    cleaned = _strip_accents(value)
    cleaned = cleaned.replace("(", "").replace(")", "").replace(".", "").strip()
    _reject_html(cleaned, "teléfono")

    # Normalizar: permitir solo dígitos, espacios y guiones, manteniendo '+' inicial si existe
    has_plus = cleaned.startswith("+")
    cleaned = re.sub(r"[^\d\s\-]", "", cleaned)
    cleaned = cleaned.strip()
    if has_plus:
        cleaned = f"+{cleaned.lstrip('+')}"

    if not PHONE_PATTERN.fullmatch(cleaned):
        raise InputValidationError("El teléfono contiene caracteres no permitidos")

    return cleaned


def sanitize_email(value: str | None, allow_empty: bool = False) -> str:
    if not value:
        if allow_empty:
            return ""
        raise InputValidationError("El email es requerido")

    cleaned = value.strip().lower()
    _reject_html(cleaned, "email")

    if not EMAIL_PATTERN.fullmatch(cleaned):
        raise InputValidationError("El email no tiene un formato válido")

    return cleaned


def sanitize_notes(value: str | None, allow_empty: bool = True, max_length: int = 240) -> str:
    if not value:
        if allow_empty:
            return ""
        raise InputValidationError("Las notas son requeridas")

    cleaned = _strip_accents(value).strip().upper()
    _reject_html(cleaned, "notas")

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]

    if not SAFE_NOTE_PATTERN.fullmatch(cleaned):
        raise InputValidationError("Las notas contienen caracteres no permitidos")

    return cleaned


def sanitize_support_description(value: str | None, max_length: int = 1000) -> str:
    if not value:
        raise InputValidationError("La descripción es requerida")

    cleaned = value.strip()
    _reject_html(cleaned, "descripción")

    # Normalizar espacios en blanco
    cleaned = re.sub(r"\s+", " ", cleaned)

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]

    # Permitir cualquier carácter excepto HTML (ya validado arriba)
    # No convertimos a mayúsculas ni removemos acentos para soporte técnico
    return cleaned
