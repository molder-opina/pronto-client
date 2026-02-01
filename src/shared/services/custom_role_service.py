"""Service for managing custom roles and permissions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from shared.db import get_session
from shared.models import CustomRole, RolePermission


class CustomRoleService:
    """Service for managing custom roles."""

    @staticmethod
    def get_all_roles(include_inactive: bool = False) -> list[dict[str, Any]]:
        """Get all custom roles."""
        with get_session() as session:
            query = select(CustomRole).options(joinedload(CustomRole.permissions))

            if not include_inactive:
                query = query.where(CustomRole.is_active)

            roles = session.execute(query.order_by(CustomRole.role_name)).unique().scalars().all()

            return [
                {
                    "id": role.id,
                    "role_code": role.role_code,
                    "role_name": role.role_name,
                    "description": role.description,
                    "color": role.color,
                    "icon": role.icon,
                    "is_active": role.is_active,
                    "created_at": role.created_at.isoformat() if role.created_at else None,
                    "updated_at": role.updated_at.isoformat() if role.updated_at else None,
                    "permissions_count": len(role.permissions),
                }
                for role in roles
            ]

    @staticmethod
    def get_role_by_id(role_id: int) -> dict[str, Any] | None:
        """Get a custom role by ID with its permissions."""
        with get_session() as session:
            role = (
                session.execute(
                    select(CustomRole)
                    .options(joinedload(CustomRole.permissions))
                    .where(CustomRole.id == role_id)
                )
                .unique()
                .scalars()
                .first()
            )

            if not role:
                return None

            return {
                "id": role.id,
                "role_code": role.role_code,
                "role_name": role.role_name,
                "description": role.description,
                "color": role.color,
                "icon": role.icon,
                "is_active": role.is_active,
                "created_at": role.created_at.isoformat() if role.created_at else None,
                "updated_at": role.updated_at.isoformat() if role.updated_at else None,
                "permissions": [
                    {
                        "id": perm.id,
                        "resource_type": perm.resource_type,
                        "action": perm.action,
                        "allowed": perm.allowed,
                        "conditions": perm.conditions,
                    }
                    for perm in role.permissions
                ],
            }

    @staticmethod
    def get_role_by_code(role_code: str) -> dict[str, Any] | None:
        """Get a custom role by code."""
        with get_session() as session:
            role = (
                session.execute(
                    select(CustomRole)
                    .options(joinedload(CustomRole.permissions))
                    .where(CustomRole.role_code == role_code)
                )
                .unique()
                .scalars()
                .first()
            )

            if not role:
                return None

            return {
                "id": role.id,
                "role_code": role.role_code,
                "role_name": role.role_name,
                "description": role.description,
                "color": role.color,
                "icon": role.icon,
                "is_active": role.is_active,
                "created_at": role.created_at.isoformat() if role.created_at else None,
                "updated_at": role.updated_at.isoformat() if role.updated_at else None,
                "permissions": [
                    {
                        "id": perm.id,
                        "resource_type": perm.resource_type,
                        "action": perm.action,
                        "allowed": perm.allowed,
                        "conditions": perm.conditions,
                    }
                    for perm in role.permissions
                ],
            }

    @staticmethod
    def create_role(data: dict[str, Any], employee_id: int | None = None) -> dict[str, Any]:
        """Create a new custom role."""
        with get_session() as session:
            # Check if role_code already exists
            existing = (
                session.execute(select(CustomRole).where(CustomRole.role_code == data["role_code"]))
                .scalars()
                .first()
            )

            if existing:
                raise ValueError(f"Role with code '{data['role_code']}' already exists")

            # Extract permissions if provided
            permissions_data = data.pop("permissions", [])

            # Create role
            role = CustomRole(**data, created_by=employee_id)
            session.add(role)
            session.flush()

            # Add permissions
            for perm_data in permissions_data:
                permission = RolePermission(custom_role_id=role.id, **perm_data)
                session.add(permission)

            session.flush()
            session.refresh(role)

            return CustomRoleService.get_role_by_id(role.id)

    @staticmethod
    def update_role(role_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing custom role."""
        with get_session() as session:
            role = (
                session.execute(select(CustomRole).where(CustomRole.id == role_id))
                .scalars()
                .first()
            )

            if not role:
                raise ValueError(f"Role with ID {role_id} not found")

            # Update role fields
            for key, value in data.items():
                if hasattr(role, key) and key not in [
                    "id",
                    "role_code",
                    "created_at",
                    "created_by",
                ]:
                    setattr(role, key, value)

            session.flush()
            session.refresh(role)

            return CustomRoleService.get_role_by_id(role.id)

    @staticmethod
    def delete_role(role_id: int) -> bool:
        """Delete a custom role (soft delete by setting is_active to False)."""
        with get_session() as session:
            role = (
                session.execute(select(CustomRole).where(CustomRole.id == role_id))
                .scalars()
                .first()
            )

            if not role:
                return False

            role.is_active = False
            session.flush()
            return True

    @staticmethod
    def add_permission(role_id: int, permission_data: dict[str, Any]) -> dict[str, Any]:
        """Add a permission to a role."""
        with get_session() as session:
            role = (
                session.execute(select(CustomRole).where(CustomRole.id == role_id))
                .scalars()
                .first()
            )

            if not role:
                raise ValueError(f"Role with ID {role_id} not found")

            permission = RolePermission(custom_role_id=role_id, **permission_data)
            session.add(permission)
            session.flush()
            session.refresh(permission)

            return {
                "id": permission.id,
                "resource_type": permission.resource_type,
                "action": permission.action,
                "allowed": permission.allowed,
                "conditions": permission.conditions,
            }

    @staticmethod
    def update_permission(permission_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a permission."""
        with get_session() as session:
            permission = (
                session.execute(select(RolePermission).where(RolePermission.id == permission_id))
                .scalars()
                .first()
            )

            if not permission:
                raise ValueError(f"Permission with ID {permission_id} not found")

            for key, value in data.items():
                if hasattr(permission, key) and key not in ["id", "custom_role_id"]:
                    setattr(permission, key, value)

            session.flush()
            session.refresh(permission)

            return {
                "id": permission.id,
                "resource_type": permission.resource_type,
                "action": permission.action,
                "allowed": permission.allowed,
                "conditions": permission.conditions,
            }

    @staticmethod
    def delete_permission(permission_id: int) -> bool:
        """Delete a permission."""
        with get_session() as session:
            permission = (
                session.execute(select(RolePermission).where(RolePermission.id == permission_id))
                .scalars()
                .first()
            )

            if not permission:
                return False

            session.delete(permission)
            session.flush()
            return True

    @staticmethod
    def bulk_update_permissions(role_id: int, permissions: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace all permissions for a role."""
        with get_session() as session:
            role = (
                session.execute(
                    select(CustomRole)
                    .options(joinedload(CustomRole.permissions))
                    .where(CustomRole.id == role_id)
                )
                .unique()
                .scalars()
                .first()
            )

            if not role:
                raise ValueError(f"Role with ID {role_id} not found")

            # Delete existing permissions
            for perm in role.permissions:
                session.delete(perm)

            session.flush()

            # Add new permissions
            for perm_data in permissions:
                permission = RolePermission(custom_role_id=role_id, **perm_data)
                session.add(permission)

            session.flush()

            return CustomRoleService.get_role_by_id(role_id)

    @staticmethod
    def check_permission(role_code: str, resource_type: str, action: str) -> bool:
        """Check if a role has permission for a specific resource and action."""
        with get_session() as session:
            role = (
                session.execute(
                    select(CustomRole)
                    .options(joinedload(CustomRole.permissions))
                    .where(CustomRole.role_code == role_code, CustomRole.is_active)
                )
                .unique()
                .scalars()
                .first()
            )

            if not role:
                return False

            for perm in role.permissions:
                if perm.resource_type == resource_type and perm.action == action:
                    return perm.allowed

            return False
