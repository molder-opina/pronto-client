"""
Input validation utilities.
"""

import re


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def validate_password(password: str) -> None:
    """
    Validate password strength.

    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    """
    if not password:
        raise ValidationError("La contraseña es requerida")

    if len(password) < 8:
        raise ValidationError("La contraseña debe tener al menos 8 caracteres")

    if not re.search(r"[A-Z]", password):
        raise ValidationError("La contraseña debe tener al menos una mayúscula")

    if not re.search(r"[a-z]", password):
        raise ValidationError("La contraseña debe tener al menos una minúscula")

    if not re.search(r"[0-9]", password):
        raise ValidationError("La contraseña debe tener al menos un número")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError("La contraseña debe tener al menos un carácter especial")


def validate_email(email: str) -> None:
    """Validate email format."""
    if not email:
        raise ValidationError("El email es requerido")

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        raise ValidationError("Formato de email inválido")


def validate_role(role: str) -> None:
    """Validate role against system roles in DB (dynamic)."""
    from shared.constants import Roles

    # 1. Check legacy constants first (optimization for standard roles)
    if role in Roles.all_values():
        return

    # 2. Check Database for custom/dynamic roles
    try:
        from sqlalchemy import select

        from shared.db import get_session
        from shared.models import SystemRole

        with get_session() as session:
            # Check if role exists in DB
            exists = session.execute(
                select(SystemRole.name).where(SystemRole.name == role)
            ).scalar()
            if exists:
                return
    except Exception:
        # Silent fail on DB check errors, fall through to error
        pass

    allowed = ", ".join(Roles.all_values())
    raise ValidationError(f"Rol inválido: {role}. (No encontrado en roles del sistema)")


def validate_pagination(page: int | None, limit: int | None) -> tuple[int, int]:
    """
    Validate and normalize pagination parameters.

    Returns: (page, limit) tuple with validated values.
    """
    from shared.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

    if page is None or page < 1:
        page = 1

    if limit is None or limit < 1:
        limit = DEFAULT_PAGE_SIZE
    elif limit > MAX_PAGE_SIZE:
        limit = MAX_PAGE_SIZE

    return page, limit
