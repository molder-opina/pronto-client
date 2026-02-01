"""Helpers to administer route based permissions (roles ABC)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shared.db import get_session
from shared.models import Employee, EmployeeRouteAccess, RoutePermission

logger = logging.getLogger(__name__)


def list_employees_with_permissions() -> list[dict[str, object]]:
    with get_session() as session:
        employees = session.execute(select(Employee).order_by(Employee.id)).scalars().all()
        permissions = session.execute(select(RoutePermission)).scalars().all()
        perms_by_id = {perm.id: perm for perm in permissions}

        data = []
        for employee in employees:
            codes = [perms_by_id[access.route_permission_id].code for access in employee.routes]
            data.append(
                {
                    "id": employee.id,
                    "name": employee.name,
                    "email": employee.email,
                    "role": employee.role,
                    "permissions": codes,
                }
            )
        # Sort by name after decryption
        return sorted(data, key=lambda x: x["name"])


def assign_permission(employee_id: int, permission_code: str) -> dict[str, object]:
    with get_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise ValueError("Empleado no encontrado")
        permission = (
            session.execute(select(RoutePermission).where(RoutePermission.code == permission_code))
            .scalars()
            .one_or_none()
        )
        if permission is None:
            raise ValueError("Permiso no encontrado")

        existing = (
            session.execute(
                select(EmployeeRouteAccess).where(
                    EmployeeRouteAccess.employee_id == employee_id,
                    EmployeeRouteAccess.route_permission_id == permission.id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if existing is None:
            try:
                session.add(EmployeeRouteAccess(employee=employee, permission=permission))
                session.flush()
            except IntegrityError:
                # Race condition: permission was assigned concurrently
                session.rollback()
                logger.warning(
                    f"Race condition detected assigning permission {permission_code} to employee {employee_id}"
                )
                # Re-fetch employee to get updated permissions
                session.refresh(employee)
        else:
            session.flush()
        session.refresh(employee)

        return {
            "employee_id": employee.id,
            "permissions": [access.permission.code for access in employee.routes],
        }


def revoke_permission(employee_id: int, permission_code: str) -> dict[str, object]:
    with get_session() as session:
        access = (
            session.execute(
                select(EmployeeRouteAccess)
                .join(EmployeeRouteAccess.permission)
                .where(
                    EmployeeRouteAccess.employee_id == employee_id,
                    RoutePermission.code == permission_code,
                )
            )
            .scalars()
            .one_or_none()
        )
        if access:
            session.delete(access)
            session.flush()

        employee = session.get(Employee, employee_id)
        if employee is None:
            raise ValueError("Empleado no encontrado")

        session.refresh(employee)

        return {
            "employee_id": employee.id,
            "permissions": [route.permission.code for route in employee.routes],
        }


def list_employees_by_permission(permission_code: str) -> list[dict[str, object]]:
    """List all employees that have a specific permission."""
    with get_session() as session:
        employees = (
            session.execute(
                select(Employee)
                .join(Employee.routes)
                .join(EmployeeRouteAccess.permission)
                .where(RoutePermission.code == permission_code, Employee.is_active.is_(True))
                .order_by(Employee.id)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": employee.id,
                "name": employee.name,
                "email": employee.email,
                "role": employee.role,
            }
            for employee in employees
        ]
