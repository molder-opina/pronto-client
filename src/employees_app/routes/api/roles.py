import re
from http import HTTPStatus

from flask import Blueprint, jsonify, request
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from shared.db import get_session
from shared.models import RolePermissionBinding, SystemPermission, SystemRole
from shared.permissions import Permission, refresh_permissions_cache, require_permission

roles_bp = Blueprint("roles", __name__)


@roles_bp.route("/roles", methods=["GET"])
@require_permission(Permission.EMPLOYEES_MANAGE_PERMISSIONS)
def list_roles():
    """List all system roles with their permissions."""
    try:
        with get_session() as db_session:
            stmt = (
                select(SystemRole)
                .options(
                    selectinload(SystemRole.permissions).selectinload(
                        RolePermissionBinding.permission
                    )
                )
                .order_by(SystemRole.id)
            )

            roles = db_session.execute(stmt).scalars().all()

            result = []
            for role in roles:
                perms = [
                    {
                        "code": binding.permission.code,
                        "category": binding.permission.category,
                        "description": binding.permission.description,
                    }
                    for binding in role.permissions
                ]

                result.append(
                    {
                        "id": role.id,
                        "name": role.name,
                        "display_name": role.display_name,
                        "description": role.description,
                        "is_custom": role.is_custom,
                        "permissions": perms,
                    }
                )

            return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@roles_bp.route("/permissions", methods=["GET"])
@require_permission(Permission.EMPLOYEES_MANAGE_PERMISSIONS)
def list_permissions():
    """List all available system permissions grouped by category."""
    try:
        with get_session() as db_session:
            stmt = select(SystemPermission).order_by(
                SystemPermission.category, SystemPermission.code
            )
            permissions = db_session.execute(stmt).scalars().all()

            data = [
                {"id": p.id, "code": p.code, "category": p.category, "description": p.description}
                for p in permissions
            ]
            return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@roles_bp.route("/roles", methods=["POST"])
@require_permission(Permission.EMPLOYEES_MANAGE_PERMISSIONS)
def create_role():
    """Create a new custom role."""
    data = request.json
    name = data.get("name")
    display_name = data.get("display_name")
    description = data.get("description")
    permission_codes = data.get("permissions", [])

    if not name or not display_name:
        return jsonify(
            {"status": "error", "message": "Name and Display Name are required"}
        ), HTTPStatus.BAD_REQUEST

    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        return jsonify(
            {
                "status": "error",
                "message": "Role name must contain only letters, numbers and underscores",
            }
        ), HTTPStatus.BAD_REQUEST

    try:
        with get_session() as db_session:
            existing = (
                db_session.execute(select(SystemRole).where(SystemRole.name == name))
                .scalars()
                .first()
            )
            if existing:
                return jsonify(
                    {"status": "error", "message": "Role name already exists"}
                ), HTTPStatus.CONFLICT

            new_role = SystemRole(
                name=name, display_name=display_name, description=description, is_custom=True
            )
            db_session.add(new_role)
            db_session.flush()

            if permission_codes:
                stmt = select(SystemPermission).where(SystemPermission.code.in_(permission_codes))
                perms_objs = db_session.execute(stmt).scalars().all()

                for p in perms_objs:
                    db_session.add(RolePermissionBinding(role_id=new_role.id, permission_id=p.id))

            db_session.commit()
            refresh_permissions_cache()

            return jsonify(
                {"status": "success", "message": "Role created", "id": new_role.id}
            ), HTTPStatus.CREATED
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@roles_bp.route("/roles/<int:role_id>", methods=["PUT"])
@require_permission(Permission.EMPLOYEES_MANAGE_PERMISSIONS)
def update_role(role_id):
    """Update role details and permissions."""
    data = request.json
    display_name = data.get("display_name")
    description = data.get("description")
    permission_codes = data.get("permissions")

    try:
        with get_session() as db_session:
            role = db_session.get(SystemRole, role_id)
            if not role:
                return jsonify(
                    {"status": "error", "message": "Role not found"}
                ), HTTPStatus.NOT_FOUND

            if display_name:
                role.display_name = display_name
            if description is not None:
                role.description = description

            if permission_codes is not None:
                if role.name == "system" and not permission_codes:
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Cannot remove all permissions from system role",
                        }
                    ), HTTPStatus.BAD_REQUEST

                db_session.execute(
                    delete(RolePermissionBinding).where(RolePermissionBinding.role_id == role_id)
                )

                if permission_codes:
                    stmt = select(SystemPermission).where(
                        SystemPermission.code.in_(permission_codes)
                    )
                    perms_objs = db_session.execute(stmt).scalars().all()

                    for p in perms_objs:
                        db_session.add(RolePermissionBinding(role_id=role.id, permission_id=p.id))

            db_session.commit()
            refresh_permissions_cache()

            return jsonify({"status": "success", "message": "Role updated"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@roles_bp.route("/roles/<int:role_id>", methods=["DELETE"])
@require_permission(Permission.EMPLOYEES_MANAGE_PERMISSIONS)
def delete_role(role_id):
    """Delete a custom role."""
    try:
        with get_session() as db_session:
            role = db_session.get(SystemRole, role_id)
            if not role:
                return jsonify(
                    {"status": "error", "message": "Role not found"}
                ), HTTPStatus.NOT_FOUND

            if not role.is_custom:
                return jsonify(
                    {"status": "error", "message": "Cannot delete system roles"}
                ), HTTPStatus.FORBIDDEN

            db_session.delete(role)
            db_session.commit()
            refresh_permissions_cache()

            return jsonify({"status": "success", "message": "Role deleted"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
