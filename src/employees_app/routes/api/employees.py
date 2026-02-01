"""
Employees API - Endpoints para gestión de empleados
Handles employee CRUD operations, roles, permissions, and tips
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from employees_app.decorators import admin_required
from shared.jwt_middleware import get_employee_id, jwt_required
from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Employee
from shared.schemas import CreateEmployeeRequest, UpdateEmployeeRequest
from shared.serializers import error_response, serialize_employee, success_response
from shared.services.employee_service import (
    create_employee,
    delete_employee,
    get_employee,
    list_employees,
    update_employee,
)
from shared.services.order_service import get_waiter_tips
from shared.services.role_service import (
    assign_permission,
    list_employees_with_permissions,
    revoke_permission,
)
from shared.validation import ValidationError

# Create blueprint without url_prefix (inherited from parent)
employees_bp = Blueprint("employees", __name__)
logger = get_logger(__name__)


# ==================== EMPLOYEES CRUD ENDPOINTS ====================


@employees_bp.get("/employees")
@admin_required
def get_all_employees():
    """
    Listar empleados con paginación

    Query params:
        - page: int (opcional)
        - limit: int (opcional)

    Requiere permisos de administrador.
    """
    page = request.args.get("page", type=int)
    limit = request.args.get("limit", type=int)
    result = list_employees(page=page, limit=limit)
    return jsonify(success_response(result))


@employees_bp.get("/employees/search")
@admin_required
def search_employees():
    """
    Buscar empleados por nombre, email o ID.
    """
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(success_response({"employees": []}))

    query_lower = query.lower()
    with get_session() as db_session:
        employees = (
            db_session.execute(select(Employee).order_by(Employee.name_encrypted, Employee.id))
            .scalars()
            .all()
        )

        matches = []
        for employee in employees:
            if (
                query_lower in str(employee.id).lower()
                or query_lower in (employee.name or "").lower()
                or query_lower in (employee.email or "").lower()
            ):
                matches.append(serialize_employee(employee))

    return jsonify(success_response({"employees": matches}))


@employees_bp.get("/employees/<int:employee_id>")
@admin_required
def get_single_employee(employee_id: int):
    """
    Obtener un empleado específico

    Requiere permisos de administrador.
    """
    employee = get_employee(employee_id)
    if employee is None:
        return jsonify(error_response("Empleado no encontrado")), HTTPStatus.NOT_FOUND
    return jsonify(success_response(employee))


@employees_bp.get("/employees/on-shift")
def get_employees_on_shift():
    """
    Obtener empleados activos con su estado de sign-in

    Retorna todos los empleados activos con información de si están actualmente
    firmados (basado en actividad reciente).
    """
    try:
        with get_session() as db_session:
            # Get all active employees, order by role and encrypted name to avoid decrypting in SQL
            employees = (
                db_session.execute(
                    select(Employee)
                    .where(Employee.is_active.is_(True))
                    .order_by(Employee.role, Employee.name_encrypted, Employee.id)
                )
                .scalars()
                .all()
            )

            employees_data = []
            for emp in employees:
                is_signed_in = emp.is_signed_in(timeout_minutes=5)  # 5 minute activity timeout
                employees_data.append(
                    {
                        "id": emp.id,
                        "name": emp.name,
                        "role": emp.role,
                        "is_active": emp.is_active if hasattr(emp, "is_active") else True,
                        "signed_in": is_signed_in,
                        "last_activity": emp.last_activity_at.isoformat()
                        if emp.last_activity_at
                        else None,
                    }
                )

            return jsonify({"employees": employees_data}), HTTPStatus.OK

    except Exception as e:
        logger.error(f"Error fetching employees on shift: {e}", exc_info=True)
        return jsonify({"employees": []}), HTTPStatus.OK


@employees_bp.post("/employees")
@admin_required
def post_create_employee():
    """
    Crear nuevo empleado

    Body: Ver CreateEmployeeRequest schema

    Requiere permisos de administrador.
    """
    payload = request.get_json(silent=True) or {}

    try:
        emp_data = CreateEmployeeRequest(**payload)
        result = create_employee(emp_data.dict())
        logger.info(f"Admin {get_employee_id()} created employee {result['id']}")
        return jsonify(success_response(result)), HTTPStatus.CREATED
    except PydanticValidationError as e:
        return jsonify(
            error_response("Datos de empleado inválidos", {"details": e.errors()})
        ), HTTPStatus.BAD_REQUEST
    except ValidationError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST


@employees_bp.put("/employees/<int:employee_id>")
@admin_required
def put_update_employee(employee_id: int):
    """
    Actualizar empleado

    Body: Ver UpdateEmployeeRequest schema

    Requiere permisos de administrador.
    """
    payload = request.get_json(silent=True) or {}

    try:
        emp_data = UpdateEmployeeRequest(**payload)
        result = update_employee(employee_id, emp_data.dict(exclude_unset=True))
        logger.info(f"Admin {get_employee_id()} updated employee {employee_id}")
        return jsonify(success_response(result))
    except PydanticValidationError as e:
        return jsonify(
            error_response("Datos de actualización inválidos", {"details": e.errors()})
        ), HTTPStatus.BAD_REQUEST
    except ValidationError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST


@employees_bp.delete("/employees/<int:employee_id>")
@admin_required
def delete_single_employee(employee_id: int):
    """
    Eliminar (desactivar) empleado

    Requiere permisos de administrador.
    """
    try:
        delete_employee(employee_id)
        logger.info(f"Admin {get_employee_id()} deactivated employee {employee_id}")
        return jsonify(success_response({"success": True}))
    except ValidationError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST


# ==================== TIPS ENDPOINTS ====================


@employees_bp.get("/employees/<int:employee_id>/tips")
@jwt_required
def get_employee_tips(employee_id: int):
    """
    Obtener propinas de un empleado

    Query params:
        - include_pending: bool - Incluir propinas pendientes

    Requiere autenticación.
    """
    include_pending = request.args.get("include_pending", "false").lower() in {"1", "true", "yes"}
    result = get_waiter_tips(employee_id, include_pending)
    if "error" in result:
        return jsonify(result), HTTPStatus.NOT_FOUND
    return jsonify(result)


# ==================== ROLES/PERMISSIONS ENDPOINTS ====================


@employees_bp.get("/roles/employees")
@admin_required
def get_roles_employees():
    """
    Listar empleados con sus roles y permisos

    Requiere permisos de administrador.
    """
    return jsonify({"employees": list_employees_with_permissions()})


@employees_bp.post("/roles/employees/<int:employee_id>/assign")
@admin_required
def post_assign_role(employee_id: int):
    """
    Asignar rol/permiso a empleado

    Body:
        {
            "permission_code": str
        }

    Requiere permisos de administrador.
    """
    payload = request.get_json(silent=True) or {}
    try:
        result = assign_permission(employee_id, payload.get("permission_code"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    return jsonify(result)


@employees_bp.post("/roles/employees/<int:employee_id>/revoke")
@admin_required
def post_revoke_role(employee_id: int):
    """
    Revocar rol/permiso de empleado

    Body:
        {
            "permission_code": str
        }

    Requiere permisos de administrador.
    """
    payload = request.get_json(silent=True) or {}
    try:
        result = revoke_permission(employee_id, payload.get("permission_code"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    return jsonify(result)


# ==================== EMPLOYEE PREFERENCES ENDPOINTS ====================


@employees_bp.get("/employees/me/preferences")
@jwt_required
def get_my_preferences():
    """
    Obtener las preferencias del empleado actual

    Retorna todas las preferencias del empleado logueado.
    """
    employee_id = get_employee_id()
    if not employee_id:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    try:
        with get_session() as db_session:
            employee = db_session.execute(
                select(Employee).where(Employee.id == employee_id)
            ).scalar_one_or_none()

            if not employee:
                return jsonify(error_response("Empleado no encontrado")), HTTPStatus.NOT_FOUND

            preferences = employee.get_preferences()
            return jsonify(success_response({"preferences": preferences}))

    except Exception as e:
        logger.error(f"Error getting preferences for employee {employee_id}: {e}", exc_info=True)
        return jsonify(
            error_response("Error al obtener preferencias")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@employees_bp.put("/employees/me/preferences")
@jwt_required
def update_my_preferences():
    """
    Actualizar una o más preferencias del empleado actual

    Body:
        {
            "key": "value",
            "another_key": "another_value"
        }

    Las preferencias enviadas se fusionan con las existentes.
    """
    employee_id = get_employee_id()
    if not employee_id:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify(error_response("No se enviaron preferencias")), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            employee = db_session.execute(
                select(Employee).where(Employee.id == employee_id)
            ).scalar_one_or_none()

            if not employee:
                return jsonify(error_response("Empleado no encontrado")), HTTPStatus.NOT_FOUND

            # Merge new preferences with existing ones
            current_prefs = employee.get_preferences()
            if not isinstance(current_prefs, dict):
                current_prefs = {}

            current_prefs.update(payload)
            employee.set_preferences(current_prefs)
            db_session.commit()

            logger.info(f"Employee {employee_id} updated preferences: {list(payload.keys())}")
            return jsonify(success_response({"preferences": current_prefs}))

    except Exception as e:
        logger.error(f"Error updating preferences for employee {employee_id}: {e}", exc_info=True)
        return jsonify(
            error_response("Error al actualizar preferencias")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@employees_bp.delete("/employees/me/preferences/<key>")
@jwt_required
def delete_my_preference(key: str):
    """
    Eliminar una preferencia específica del empleado actual

    Path params:
        - key: Nombre de la preferencia a eliminar
    """
    employee_id = get_employee_id()
    if not employee_id:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    try:
        with get_session() as db_session:
            employee = db_session.execute(
                select(Employee).where(Employee.id == employee_id)
            ).scalar_one_or_none()

            if not employee:
                return jsonify(error_response("Empleado no encontrado")), HTTPStatus.NOT_FOUND

            current_prefs = employee.get_preferences()
            if key in current_prefs:
                del current_prefs[key]
                employee.set_preferences(current_prefs)
                db_session.commit()
                logger.info(f"Employee {employee_id} deleted preference: {key}")

            return jsonify(success_response({"preferences": current_prefs}))

    except Exception as e:
        logger.error(f"Error deleting preference for employee {employee_id}: {e}", exc_info=True)
        return jsonify(
            error_response("Error al eliminar preferencia")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
