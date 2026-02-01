"""Centralized authentication and permission helpers."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from sqlalchemy import select

from shared.db import get_session
from shared.models import Employee
from shared.security import hash_identifier


class AuthError(Exception):
    """Raised when an authentication or authorization error occurs."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.UNAUTHORIZED) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class EmployeeData:
    """Simple data class to hold employee information outside of database session."""

    id: int
    name: str
    email: str
    role: str
    additional_roles: str | None


@dataclass
class AuthResult:
    employee: EmployeeData


class AuthService:
    """Provides utilities to authenticate employees and check permissions."""

    @staticmethod
    def authenticate(email: str, password: str) -> AuthResult:
        email_hash = hash_identifier(email)
        with get_session() as session:
            employee = (
                session.execute(
                    select(Employee).where(
                        Employee.email_hash == email_hash, Employee.is_active.is_(True)
                    )
                )
                .scalars()
                .one_or_none()
            )
            if employee is None:
                raise AuthError("Credenciales inválidas", status=HTTPStatus.UNAUTHORIZED)

            # Verify password while employee is still attached to session
            if not employee.verify_password(password):
                raise AuthError("Credenciales inválidas", status=HTTPStatus.UNAUTHORIZED)

            # Extract all required data while employee is still in session
            # Create a simple data object that doesn't require a database session
            employee_data = EmployeeData(
                id=employee.id,
                name=employee.name,
                email=employee.email,
                role=employee.role,
                additional_roles=employee.additional_roles,
            )

            return AuthResult(employee=employee_data)

    @staticmethod
    def has_role(employee, role: str) -> bool:
        """Return True when the employee has the requested role or is a super admin.

        Args:
            employee: Either an Employee model instance or EmployeeData dataclass
            role: The role to check
        """
        if employee.role == Roles.SUPER_ADMIN:
            return True
        return employee.role == role


class Roles:
    WAITER = "waiter"
    CHEF = "chef"
    CASHIER = "cashier"
    CONTENT_MANAGER = "content_manager"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    SYSTEM = "system"
