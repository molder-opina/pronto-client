"""
Authentication Service - Separa la lógica de autenticación del modelo Employee.

Este módulo implementa el patrón Service para gestionar:
- Verificación de credenciales
- Gestión de sesiones
- Validación de estados de cuenta
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Employee
from shared.security import hash_credentials, hash_identifier, verify_credentials

logger = get_logger(__name__)


class AuthenticationError(Exception):
    """Error raised when authentication fails."""

    def __init__(self, message: str, error_code: str = "AUTH_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class AuthServiceError(Exception):
    """Error raised when auth service operations fail."""


@dataclass
class AuthResult:
    """Resultado de una operación de autenticación."""

    success: bool
    employee: Employee | None = None
    error_message: str | None = None
    error_code: str | None = None


class AuthService:
    """
    Servicio de autenticación para empleados.

    Responsibilities:
    - Validar credenciales
    - Gestionar estado de sesión (sign-in/sign-out)
    - Verificar estado de cuenta activa
    - Manejar timeouts de sesión
    """

    SESSION_TIMEOUT_MINUTES = 5
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_WINDOW_SECONDS = 300  # 5 minutos

    def __init__(self, db_session: Session | None = None):
        self._db_session = db_session

    def _get_session(self) -> Session:
        """Obtiene una sesión de base de datos."""
        if self._db_session:
            return self._db_session
        return next(get_session())

    def authenticate(
        self,
        email: str,
        password: str,
        raise_on_failure: bool = False,
    ) -> AuthResult:
        """
        Autentica un empleado con email y contraseña.

        Args:
            email: Email del empleado
            password: Contraseña en texto plano
            raise_on_failure: Si True, lanza excepción en lugar de retornar error

        Returns:
            AuthResult con el resultado de la autenticación
        """
        try:
            session = self._get_session()

            # Normalizar email
            email_hash = hash_identifier(email)

            # Buscar empleado
            employee = session.query(Employee).filter(Employee.email_hash == email_hash).first()

            if not employee:
                logger.warning(f"Login failed: No employee found for email hash {email_hash}")
                if raise_on_failure:
                    raise AuthenticationError("Credenciales inválidas", "USER_NOT_FOUND")
                return AuthResult(
                    success=False,
                    error_message="Credenciales inválidas",
                    error_code="USER_NOT_FOUND",
                )

            # Verificar cuenta activa
            if not employee.is_active:
                logger.warning(f"Login failed: Inactive account for email hash {email_hash}")
                if raise_on_failure:
                    raise AuthenticationError("Cuenta desactivada", "ACCOUNT_INACTIVE")
                return AuthResult(
                    success=False,
                    error_message="Cuenta desactivada. Contacte al administrador",
                    error_code="ACCOUNT_INACTIVE",
                )

            # Verificar contraseña
            if not verify_credentials(email, password, employee.auth_hash):
                logger.warning(f"Login failed: Invalid password for email hash {email_hash}")
                if raise_on_failure:
                    raise AuthenticationError("Credenciales inválidas", "INVALID_PASSWORD")
                return AuthResult(
                    success=False,
                    error_message="Credenciales inválidas",
                    error_code="INVALID_PASSWORD",
                )

            # Autenticación exitosa
            logger.info(
                f"Login successful: Employee {employee.name} (ID: {employee.id}, Role: {employee.role})"
            )
            return AuthResult(success=True, employee=employee)

        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            if raise_on_failure:
                raise AuthServiceError(f"Error de autenticación: {e}")
            return AuthResult(
                success=False,
                error_message="Error de autenticación",
                error_code="AUTH_ERROR",
            )

    def sign_in(self, employee: Employee) -> None:
        """
        Registra el inicio de sesión de un empleado.

        Args:
            employee: Instancia del empleado
        """
        now = datetime.utcnow()
        employee.signed_in_at = now
        employee.last_activity_at = now
        self._get_session().commit()
        logger.info(f"Employee {employee.id} signed in at {now}")

    def sign_out(self, employee: Employee) -> None:
        """
        Registra el cierre de sesión de un empleado.

        Args:
            employee: Instancia del empleado
        """
        employee.signed_in_at = None
        employee.last_activity_at = None
        self._get_session().commit()
        logger.info(f"Employee {employee.id} signed out")

    def update_activity(self, employee: Employee) -> None:
        """
        Actualiza el timestamp de última actividad.

        Args:
            employee: Instancia del empleado
        """
        employee.last_activity_at = datetime.utcnow()
        self._get_session().commit()

    def is_signed_in(self, employee: Employee, timeout_minutes: int | None = None) -> bool:
        """
        Verifica si un empleado tiene sesión activa.

        Args:
            employee: Instancia del empleado
            timeout_minutes: Timeout de inactividad (usa valor por defecto si es None)

        Returns:
            True si tiene sesión activa y dentro del timeout
        """
        if not employee.signed_in_at or not employee.last_activity_at:
            return False

        timeout = timedelta(minutes=timeout_minutes or self.SESSION_TIMEOUT_MINUTES)
        now = datetime.utcnow()

        return (now - employee.last_activity_at) <= timeout

    def set_password(self, employee: Employee, password: str) -> None:
        """
        Establece la contraseña de un empleado.

        Args:
            employee: Instancia del empleado
            password: Nueva contraseña en texto plano
        """
        if password is None:
            raise ValueError("password must not be None")
        employee.auth_hash = hash_credentials(employee.email, password)
        self._get_session().commit()
        logger.info(f"Password updated for employee {employee.id}")

    def verify_password(self, employee: Employee, password: str) -> bool:
        """
        Verifica la contraseña de un empleado.

        Args:
            employee: Instancia del empleado
            password: Contraseña a verificar

        Returns:
            True si la contraseña es correcta
        """
        return verify_credentials(employee.email, password, employee.auth_hash)

    def get_session_data(self, employee: Employee) -> dict[str, Any]:
        """
        Obtiene los datos de sesión para almacenar en Flask session.

        Args:
            employee: Instancia del empleado

        Returns:
            Dict con los datos de sesión
        """
        return {
            "employee_id": employee.id,
            "employee_name": employee.name,
            "employee_email": employee.email,
            "employee_role": employee.role,
            "employee_additional_roles": employee.additional_roles or None,
            "employee_scopes": employee.get_scopes(),
        }


# Instancia global del servicio
auth_service = AuthService()
