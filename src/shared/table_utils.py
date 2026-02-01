"""
Utilities for building and validating table codes.

Format: <AREA>-MNN
- AREA: 1-3 alphanumeric characters (uppercase, no spaces)
- NN: table number 01-99 (two digits)
Regex: ^[A-Z0-9]{1,3}-M(0[1-9]|[1-9][0-9])$
"""

from __future__ import annotations

import re

from shared.validation import ValidationError

TABLE_CODE_REGEX = re.compile(r"^[A-Z0-9]{1,3}-M(0[1-9]|[1-9][0-9])$")


def normalize_area_code(area_code: str) -> str:
    """Sanitize area code to at most 3 uppercase alphanumeric characters."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (area_code or "").strip()).upper()
    return cleaned[:3]


def build_table_code(area_code: str, table_number: int) -> str:
    """Build a short code like B-M01 validating inputs."""
    normalized_area = normalize_area_code(area_code)
    if not normalized_area:
        raise ValidationError("El código de área es obligatorio (1 a 3 caracteres alfanuméricos).")
    if len(normalized_area) > 3:
        raise ValidationError("El código de área no puede exceder 3 caracteres.")

    if not isinstance(table_number, int) or table_number < 1 or table_number > 99:
        raise ValidationError("El número de mesa debe ser un entero entre 1 y 99.")

    code = f"{normalized_area}-M{table_number:02d}"
    validate_table_code(code)
    return code


def validate_table_code(table_code: str) -> str:
    """Validate a table code; returns the normalized code or raises ValidationError."""
    normalized = (table_code or "").strip().upper()
    if not TABLE_CODE_REGEX.match(normalized):
        raise ValidationError("El código de mesa es inválido. Usa el formato AREA-MNN (ej. B-M01).")
    return normalized


def parse_table_code(table_code: str) -> tuple[str, int] | None:
    """
    Parse a table code and return (area_code, table_number) or None if invalid.
    Does not raise.
    """
    normalized = (table_code or "").strip().upper()
    match = TABLE_CODE_REGEX.match(normalized)
    if not match:
        return None
    area_part = normalized.split("-")[0]
    table_number = int(match.group(1))
    return area_part, table_number


def derive_area_code(label: str | None, fallback: str = "G") -> str:
    """
    Derive a 1-3 char area code from a human label (e.g. 'Barra', 'VIP', 'Terraza').
    """
    base = (label or "").strip().lower()
    if base.startswith("vip"):
        return "V"
    if base.startswith("barra") or base.startswith("bar"):
        return "B"
    if base.startswith("mesa"):
        return "M"
    derived = normalize_area_code(label or "")
    if derived:
        return derived
    fallback_normalized = normalize_area_code(fallback or "G")
    return fallback_normalized or "G"
