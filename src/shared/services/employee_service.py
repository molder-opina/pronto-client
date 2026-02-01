"""Service for managing employee records."""

from __future__ import annotations

from sqlalchemy import func, select

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Employee
from shared.security import hash_credentials, hash_identifier
from shared.serializers import paginated_response, serialize_employee
from shared.validation import ValidationError, validate_pagination, validate_password, validate_role

logger = get_logger(__name__)


def list_employees(page: int | None = None, limit: int | None = None) -> dict[str, object]:
    """List all employees with pagination."""
    page, limit = validate_pagination(page, limit)
    offset = (page - 1) * limit

    with get_session() as session:
        total = session.scalar(select(func.count()).select_from(Employee))

        stmt = (
            select(Employee)
            .order_by(Employee.role, Employee.name_encrypted, Employee.id)
            .limit(limit)
            .offset(offset)
        )
        employees = session.execute(stmt).scalars().all()

        items = [serialize_employee(emp) for emp in employees]
        logger.info(f"Listed {len(items)} employees (page {page}, total {total})")

        return paginated_response(items, total, page, limit)


def get_employee(employee_id: int) -> dict[str, object] | None:
    """Get a single employee by ID."""
    with get_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            logger.warning(f"Employee {employee_id} not found")
            return None
        return serialize_employee(employee)


def create_employee(data: dict[str, object]) -> dict[str, object]:
    """Create a new employee."""
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "staff")

    if not name or not email or not password:
        raise ValidationError("Nombre, email y contraseña son requeridos")

    validate_password(password)
    validate_role(role)

    with get_session() as session:
        email_hash = hash_identifier(email)
        existing = (
            session.execute(select(Employee).where(Employee.email_hash == email_hash))
            .scalars()
            .one_or_none()
        )
        if existing:
            logger.warning(f"Attempt to create employee with duplicate email: {email}")
            raise ValidationError("Ya existe un empleado con este email")

        employee = Employee()
        employee.name = name
        employee.email = email
        employee.role = role
        employee.is_active = data.get("is_active", True)
        employee.auth_hash = hash_credentials(employee.email, password)

        session.add(employee)
        session.flush()
        session.refresh(employee)

        logger.info(f"Created employee {employee.id}: {employee.name} ({employee.role})")
        return serialize_employee(employee)


def update_employee(employee_id: int, data: dict[str, object]) -> dict[str, object]:
    """Update an existing employee."""
    if data.get("password"):
        validate_password(data["password"])
    if "role" in data:
        validate_role(data["role"])

    with get_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            logger.warning(f"Attempt to update non-existent employee {employee_id}")
            raise ValidationError("Empleado no encontrado")

        if "name" in data:
            employee.name = data["name"]

        if "email" in data:
            existing = (
                session.execute(
                    select(Employee).where(
                        Employee.email_hash == hash_identifier(data["email"]),
                        Employee.id != employee_id,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if existing:
                logger.warning(
                    f"Attempt to update employee {employee_id} with duplicate email: {data['email']}"
                )
                raise ValidationError("Ya existe un empleado con este email")
            employee.email = data["email"]

        if "role" in data:
            employee.role = data["role"]
        if "is_active" in data:
            employee.is_active = data["is_active"]
        if data.get("password"):
            employee.auth_hash = hash_credentials(employee.email, data["password"])

        session.flush()
        session.refresh(employee)

        logger.info(f"Updated employee {employee.id}: {employee.name}")
        return serialize_employee(employee)


def delete_employee(employee_id: int) -> bool:
    """Delete (deactivate) an employee."""
    with get_session() as session:
        employee = session.get(Employee, employee_id)
        if employee is None:
            logger.warning(f"Attempt to delete non-existent employee {employee_id}")
            raise ValidationError("Empleado no encontrado")

        employee.is_active = False
        session.flush()

        logger.info(f"Deactivated employee {employee.id}: {employee.name}")
        return True
