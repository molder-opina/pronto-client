"""
Sistema de permisos granular para empleados

Este módulo define permisos específicos basados en capacidades
en lugar de roles rígidos. Cada rol se traduce en un conjunto de permisos.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from http import HTTPStatus

from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.db import get_session
from shared.models import RolePermissionBinding, SystemRole

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """Permisos disponibles en el sistema"""

    # Permisos de productos/menú
    MENU_VIEW = "menu:view"
    MENU_CREATE = "menu:create"
    MENU_EDIT = "menu:edit"
    MENU_DELETE = "menu:delete"
    MENU_TOGGLE_AVAILABILITY = "menu:toggle_availability"
    MENU_EDIT_PREP_TIME = "menu:edit_prep_time"
    MENU_EDIT_PRICE = "menu:edit_price"

    # Permisos de órdenes
    ORDERS_VIEW = "orders:view"
    ORDERS_ACCEPT = "orders:accept"
    ORDERS_MODIFY = "orders:modify"
    ORDERS_CANCEL = "orders:cancel"
    ORDERS_DELIVER = "orders:deliver"

    # Permisos de cocina
    KITCHEN_VIEW = "kitchen:view"
    KITCHEN_START = "kitchen:start"
    KITCHEN_COMPLETE = "kitchen:complete"

    # Permisos de cobro
    PAYMENTS_VIEW = "payments:view"
    PAYMENTS_PROCESS = "payments:process"
    PAYMENTS_TIP = "payments:tip"
    PAYMENTS_REFUND = "payments:refund"

    # Permisos de reportes
    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"
    REPORTS_ADVANCED = "reports:advanced"

    # Permisos de empleados
    EMPLOYEES_VIEW = "employees:view"
    EMPLOYEES_CREATE = "employees:create"
    EMPLOYEES_EDIT = "employees:edit"
    EMPLOYEES_DELETE = "employees:delete"
    EMPLOYEES_MANAGE_PERMISSIONS = "employees:manage_permissions"

    # Permisos de configuración
    CONFIG_VIEW = "config:view"
    CONFIG_EDIT = "config:edit"
    CONFIG_ADVANCED = "config:advanced"

    # Permisos de mesas
    TABLES_VIEW = "tables:view"
    TABLES_EDIT = "tables:edit"

    # Permisos de clientes
    CUSTOMERS_VIEW = "customers:view"
    CUSTOMERS_EDIT = "customers:edit"


# Mapeo de roles a permisos
ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "system": {
        # System (Super Admin) tiene todos los permisos
        *list(Permission)
    },
    "super_admin": {
        # Super Admin tiene todos los permisos
        *list(Permission)
    },
    "admin": {
        # Administrador tiene casi todos excepto permisos de sistema críticos
        Permission.MENU_VIEW,
        Permission.MENU_CREATE,
        Permission.MENU_EDIT,
        Permission.MENU_DELETE,
        Permission.MENU_TOGGLE_AVAILABILITY,
        Permission.MENU_EDIT_PREP_TIME,
        Permission.MENU_EDIT_PRICE,
        Permission.ORDERS_VIEW,
        Permission.ORDERS_ACCEPT,
        Permission.ORDERS_MODIFY,
        Permission.ORDERS_CANCEL,
        Permission.ORDERS_DELIVER,
        Permission.KITCHEN_VIEW,
        Permission.KITCHEN_START,
        Permission.KITCHEN_COMPLETE,
        Permission.PAYMENTS_VIEW,
        Permission.PAYMENTS_PROCESS,
        Permission.PAYMENTS_TIP,
        Permission.PAYMENTS_REFUND,
        Permission.REPORTS_VIEW,
        Permission.REPORTS_EXPORT,
        Permission.REPORTS_ADVANCED,
        Permission.EMPLOYEES_VIEW,
        Permission.EMPLOYEES_CREATE,
        Permission.EMPLOYEES_EDIT,
        Permission.CONFIG_VIEW,
        Permission.CONFIG_EDIT,
        Permission.TABLES_VIEW,
        Permission.TABLES_EDIT,
        Permission.CUSTOMERS_VIEW,
        Permission.CUSTOMERS_EDIT,
    },
    "waiter": {
        # Meseros pueden gestionar menú, órdenes y cobros básicos
        Permission.MENU_VIEW,
        Permission.MENU_CREATE,
        Permission.MENU_EDIT,
        Permission.MENU_TOGGLE_AVAILABILITY,
        Permission.MENU_EDIT_PREP_TIME,  # Los meseros pueden editar tiempos
        Permission.ORDERS_VIEW,
        Permission.ORDERS_ACCEPT,
        Permission.ORDERS_MODIFY,
        Permission.ORDERS_DELIVER,
        Permission.PAYMENTS_VIEW,
        Permission.PAYMENTS_PROCESS,
        Permission.PAYMENTS_TIP,
        Permission.TABLES_VIEW,
        Permission.CUSTOMERS_VIEW,
    },
    "chef": {
        # Chefs manejan cocina y pueden editar menú
        Permission.MENU_VIEW,
        Permission.MENU_CREATE,
        Permission.MENU_EDIT,
        Permission.MENU_TOGGLE_AVAILABILITY,
        Permission.MENU_EDIT_PREP_TIME,  # Los chefs pueden editar tiempos
        Permission.ORDERS_VIEW,
        Permission.KITCHEN_VIEW,
        Permission.KITCHEN_START,
        Permission.KITCHEN_COMPLETE,
    },
    "cashier": {
        # Cajeros manejan cobros y pueden ver órdenes
        Permission.ORDERS_VIEW,
        Permission.PAYMENTS_VIEW,
        Permission.PAYMENTS_PROCESS,
        Permission.PAYMENTS_TIP,
        Permission.PAYMENTS_REFUND,
        Permission.CUSTOMERS_VIEW,
        Permission.REPORTS_VIEW,
    },
    "content_manager": {
        # Gestores de contenido manejan menú y configuración básica
        Permission.MENU_VIEW,
        Permission.MENU_CREATE,
        Permission.MENU_EDIT,
        Permission.MENU_DELETE,
        Permission.MENU_TOGGLE_AVAILABILITY,
        Permission.MENU_EDIT_PREP_TIME,
        Permission.MENU_EDIT_PRICE,
        Permission.CONFIG_VIEW,
        Permission.CONFIG_EDIT,
    },
}


# Cache en memoria para evitar consultas constantes a DB
_PERMISSIONS_CACHE = {}
_CACHE_TIMESTAMP = None
_CACHE_TTL = timedelta(minutes=5)


def refresh_permissions_cache():
    """Recarga los permisos desde la base de datos"""
    global _PERMISSIONS_CACHE, _CACHE_TIMESTAMP
    try:
        with get_session() as session:
            stmt = select(SystemRole).options(
                selectinload(SystemRole.permissions).selectinload(RolePermissionBinding.permission)
            )
            roles = session.execute(stmt).scalars().all()

            new_cache = {}
            for role in roles:
                perms = set()
                for binding in role.permissions:
                    try:
                        # Intentar convertir el código de permiso al Enum
                        perms.add(Permission(binding.permission.code))
                    except ValueError:
                        # Si el permiso en DB no existe en el Enum del código actual, ignorar
                        pass
                new_cache[role.name] = perms

            _PERMISSIONS_CACHE = new_cache
            _CACHE_TIMESTAMP = datetime.utcnow()
    except Exception as e:
        # En caso de error (ej: tabla no existe durante init), loguear y seguir
        logger.warning(f"Error loading permissions from DB: {e}")


def get_permissions_for_role(role: str) -> set[Permission]:
    """
    Obtiene todos los permisos para un rol específico.
    Intenta leer de caché DB, y hace fallback a configuración estática.

    Args:
        role: Nombre del rol

    Returns:
        Set de permisos para el rol
    """
    role_key = role.lower() if role else ""
    if not role_key:
        return set()

    # Verificar caché y recargar si es necesario
    now = datetime.utcnow()
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or (now - _CACHE_TIMESTAMP) > _CACHE_TTL:
        refresh_permissions_cache()

    # Retornar de caché; si está vacío, hacer fallback al mapa estático
    cached_permissions = _PERMISSIONS_CACHE.get(role_key)
    if cached_permissions:
        return cached_permissions

    return ROLE_PERMISSIONS.get(role_key, set())


def has_permission(role: str, permission: Permission) -> bool:
    """
    Verifica si un rol tiene un permiso específico

    Args:
        role: Nombre del rol
        permission: Permiso a verificar

    Returns:
        True si el rol tiene el permiso
    """
    permissions = get_permissions_for_role(role)
    return permission in permissions


def has_any_permission(role: str, permissions: set[Permission]) -> bool:
    """
    Verifica si un rol tiene al menos uno de los permisos especificados

    Args:
        role: Nombre del rol
        permissions: Set de permisos a verificar

    Returns:
        True si el rol tiene al menos uno de los permisos
    """
    role_permissions = get_permissions_for_role(role)
    return bool(role_permissions & permissions)


def has_all_permissions(role: str, permissions: set[Permission]) -> bool:
    """
    Verifica si un rol tiene todos los permisos especificados

    Args:
        role: Nombre del rol
        permissions: Set de permisos a verificar

    Returns:
        True si el rol tiene todos los permisos
    """
    role_permissions = get_permissions_for_role(role)
    return permissions.issubset(role_permissions)


def require_permission(*permissions: Permission):
    """
    Decorador para verificar permisos en endpoints

    Uso:
        @require_permission(Permission.MENU_EDIT)
        def edit_menu():
            pass

        @require_permission(Permission.MENU_EDIT, Permission.MENU_EDIT_PREP_TIME)
        def edit_prep_time():
            pass
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from shared.jwt_middleware import get_current_user

            user = get_current_user()
            user_role = user.get("employee_role") if user else None

            if not user_role:
                return jsonify(
                    {"error": "Unauthorized", "message": "No authenticated user"}
                ), HTTPStatus.UNAUTHORIZED

            # Verificar si tiene alguno de los permisos requeridos
            if not has_any_permission(user_role, set(permissions)):
                return jsonify(
                    {
                        "error": "Forbidden",
                        "message": "You do not have permission to perform this action",
                        "required_permissions": [p.value for p in permissions],
                    }
                ), HTTPStatus.FORBIDDEN

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_user_permissions(role: str) -> dict:
    """
    Obtiene información de permisos para enviar al frontend

    Args:
        role: Nombre del rol

    Returns:
        Diccionario con información de permisos agrupada
    """
    permissions = get_permissions_for_role(role)

    return {
        "role": role,
        "permissions": [p.value for p in permissions],
        "capabilities": {
            "menu": {
                "view": Permission.MENU_VIEW in permissions,
                "create": Permission.MENU_CREATE in permissions,
                "edit": Permission.MENU_EDIT in permissions,
                "delete": Permission.MENU_DELETE in permissions,
                "toggle_availability": Permission.MENU_TOGGLE_AVAILABILITY in permissions,
                "edit_prep_time": Permission.MENU_EDIT_PREP_TIME in permissions,
                "edit_price": Permission.MENU_EDIT_PRICE in permissions,
            },
            "orders": {
                "view": Permission.ORDERS_VIEW in permissions,
                "accept": Permission.ORDERS_ACCEPT in permissions,
                "modify": Permission.ORDERS_MODIFY in permissions,
                "cancel": Permission.ORDERS_CANCEL in permissions,
                "deliver": Permission.ORDERS_DELIVER in permissions,
            },
            "kitchen": {
                "view": Permission.KITCHEN_VIEW in permissions,
                "start": Permission.KITCHEN_START in permissions,
                "complete": Permission.KITCHEN_COMPLETE in permissions,
            },
            "payments": {
                "view": Permission.PAYMENTS_VIEW in permissions,
                "process": Permission.PAYMENTS_PROCESS in permissions,
                "tip": Permission.PAYMENTS_TIP in permissions,
                "refund": Permission.PAYMENTS_REFUND in permissions,
            },
            "reports": {
                "view": Permission.REPORTS_VIEW in permissions,
                "export": Permission.REPORTS_EXPORT in permissions,
                "advanced": Permission.REPORTS_ADVANCED in permissions,
            },
            "employees": {
                "view": Permission.EMPLOYEES_VIEW in permissions,
                "create": Permission.EMPLOYEES_CREATE in permissions,
                "edit": Permission.EMPLOYEES_EDIT in permissions,
                "delete": Permission.EMPLOYEES_DELETE in permissions,
                "manage_permissions": Permission.EMPLOYEES_MANAGE_PERMISSIONS in permissions,
            },
            "config": {
                "view": Permission.CONFIG_VIEW in permissions,
                "edit": Permission.CONFIG_EDIT in permissions,
                "advanced": Permission.CONFIG_ADVANCED in permissions,
            },
            "tables": {
                "view": Permission.TABLES_VIEW in permissions,
                "edit": Permission.TABLES_EDIT in permissions,
            },
            "customers": {
                "view": Permission.CUSTOMERS_VIEW in permissions,
                "edit": Permission.CUSTOMERS_EDIT in permissions,
            },
        },
    }
