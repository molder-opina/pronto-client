"""
Area Service - Gestión de áreas/zonas del restaurante

Este servicio maneja la creación, actualización, eliminación y consulta
de áreas del restaurante (Terraza, Interior, VIP, Bar, etc.).
"""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload

from shared.db import get_session
from shared.logging_config import get_logger
from shared.models import Area, Table
from shared.validation import ValidationError

logger = get_logger(__name__)


class AreaService:
    """Service for managing restaurant areas/zones."""

    @staticmethod
    def list_areas(
        include_inactive: bool = False, include_table_count: bool = True
    ) -> list[dict[str, Any]]:
        """
        List all areas with optional table counts.

        Args:
            include_inactive: Whether to include inactive areas
            include_table_count: Whether to include count of tables in each area

        Returns:
            List of area dictionaries with their information
        """
        with get_session() as db_session:
            query = select(Area)

            if not include_inactive:
                query = query.where(Area.is_active)

            query = query.order_by(Area.name)
            areas = db_session.execute(query).scalars().all()

            result = []
            for area in areas:
                area_dict = {
                    "id": area.id,
                    "name": area.name,
                    "description": area.description,
                    "color": area.color,
                    "prefix": area.prefix,
                    "background_image": area.background_image,
                    "is_active": area.is_active,
                    "created_at": area.created_at.isoformat() if area.created_at else None,
                    "updated_at": area.updated_at.isoformat() if area.updated_at else None,
                }

                if include_table_count:
                    count = (
                        db_session.execute(
                            select(func.count(Table.id))
                            .where(Table.area_id == area.id)
                            .where(Table.is_active)
                        ).scalar()
                        or 0
                    )
                    area_dict["tables_count"] = count

                result.append(area_dict)

            return result

    @staticmethod
    def get_area(area_id: int) -> dict[str, Any] | None:
        """
        Get a single area by ID.

        Args:
            area_id: ID of the area to retrieve

        Returns:
            Area dictionary or None if not found
        """
        with get_session() as db_session:
            area = (
                db_session.execute(
                    select(Area).where(Area.id == area_id).options(joinedload(Area.tables))
                )
                .scalars()
                .one_or_none()
            )

            if not area:
                return None

            return {
                "id": area.id,
                "name": area.name,
                "description": area.description,
                "color": area.color,
                "prefix": area.prefix,
                "background_image": area.background_image,
                "is_active": area.is_active,
                "created_at": area.created_at.isoformat() if area.created_at else None,
                "updated_at": area.updated_at.isoformat() if area.updated_at else None,
                "tables": [
                    {
                        "id": table.id,
                        "table_number": table.table_number,
                        "status": table.status,
                        "capacity": table.capacity,
                    }
                    for table in area.tables
                    if table.is_active
                ],
            }

    @staticmethod
    def create_area(data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new area.

        Args:
            data: Dictionary with area information
                - name (required): Area name
                - description (optional): Area description
                - color (optional): Color code for UI (default: #ff6b35)
                - prefix (required): Prefix for table codes
                - background_image (optional): Base64 encoded image

        Returns:
            Created area dictionary

        Raises:
            ValidationError: If validation fails
        """
        # Validate required fields
        if not data.get("name"):
            raise ValidationError("El nombre del área es requerido")

        if not data.get("prefix"):
            raise ValidationError("El prefijo del área es requerido")

        # Validate prefix format (should be 1-3 uppercase letters)
        prefix = data["prefix"].strip().upper()
        if not prefix.isalpha() or len(prefix) > 10:
            raise ValidationError("El prefijo debe contener solo letras (máximo 10 caracteres)")

        with get_session() as db_session:
            # Check for duplicate name
            existing_name = (
                db_session.execute(select(Area).where(Area.name == data["name"]))
                .scalars()
                .one_or_none()
            )

            if existing_name:
                raise ValidationError(f"Ya existe un área con el nombre '{data['name']}'")

            # Check for duplicate prefix
            existing_prefix = (
                db_session.execute(select(Area).where(Area.prefix == prefix))
                .scalars()
                .one_or_none()
            )

            if existing_prefix:
                raise ValidationError(f"Ya existe un área con el prefijo '{prefix}'")

            # Create new area
            new_area = Area(
                name=data["name"].strip(),
                description=data.get("description", "").strip() or None,
                color=data.get("color", "#ff6b35"),
                prefix=prefix,
                background_image=data.get("background_image"),
                is_active=True,
            )

            db_session.add(new_area)
            db_session.commit()
            db_session.refresh(new_area)

            logger.info(f"Area created: {new_area.name} (ID: {new_area.id})")

            return {
                "id": new_area.id,
                "name": new_area.name,
                "description": new_area.description,
                "color": new_area.color,
                "prefix": new_area.prefix,
                "background_image": new_area.background_image,
                "is_active": new_area.is_active,
                "created_at": new_area.created_at.isoformat() if new_area.created_at else None,
                "updated_at": new_area.updated_at.isoformat() if new_area.updated_at else None,
                "tables_count": 0,
            }

    @staticmethod
    def update_area(area_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Update an existing area.

        Args:
            area_id: ID of the area to update
            data: Dictionary with fields to update

        Returns:
            Updated area dictionary

        Raises:
            ValidationError: If validation fails or area not found
        """
        with get_session() as db_session:
            area = (
                db_session.execute(select(Area).where(Area.id == area_id)).scalars().one_or_none()
            )

            if not area:
                raise ValidationError("Área no encontrada")

            # Update name if provided
            if data.get("name"):
                new_name = data["name"].strip()
                if new_name != area.name:
                    # Check for duplicate
                    existing = (
                        db_session.execute(
                            select(Area).where(Area.name == new_name).where(Area.id != area_id)
                        )
                        .scalars()
                        .one_or_none()
                    )

                    if existing:
                        raise ValidationError(f"Ya existe un área con el nombre '{new_name}'")

                    area.name = new_name

            # Update prefix if provided
            if data.get("prefix"):
                new_prefix = data["prefix"].strip().upper()
                if not new_prefix.isalpha() or len(new_prefix) > 10:
                    raise ValidationError(
                        "El prefijo debe contener solo letras (máximo 10 caracteres)"
                    )

                if new_prefix != area.prefix:
                    # Check for duplicate
                    existing = (
                        db_session.execute(
                            select(Area).where(Area.prefix == new_prefix).where(Area.id != area_id)
                        )
                        .scalars()
                        .one_or_none()
                    )

                    if existing:
                        raise ValidationError(f"Ya existe un área con el prefijo '{new_prefix}'")

                    area.prefix = new_prefix

            # Update other fields
            if "description" in data:
                area.description = data["description"].strip() if data["description"] else None

            if "color" in data:
                area.color = data["color"]

            if "background_image" in data:
                area.background_image = data["background_image"]

            if "is_active" in data:
                area.is_active = bool(data["is_active"])

            db_session.commit()
            db_session.refresh(area)

            logger.info(f"Area updated: {area.name} (ID: {area.id})")

            # Get table count
            table_count = (
                db_session.execute(
                    select(func.count(Table.id))
                    .where(Table.area_id == area.id)
                    .where(Table.is_active)
                ).scalar()
                or 0
            )

            return {
                "id": area.id,
                "name": area.name,
                "description": area.description,
                "color": area.color,
                "prefix": area.prefix,
                "background_image": area.background_image,
                "is_active": area.is_active,
                "created_at": area.created_at.isoformat() if area.created_at else None,
                "updated_at": area.updated_at.isoformat() if area.updated_at else None,
                "tables_count": table_count,
            }

    @staticmethod
    def delete_area(area_id: int, force: bool = False) -> dict[str, Any]:
        """
        Delete an area (soft delete by default).

        Args:
            area_id: ID of the area to delete
            force: If True, performs hard delete and removes all associated tables

        Returns:
            Success confirmation dictionary

        Raises:
            ValidationError: If area not found or has associated tables (when not forcing)
        """
        with get_session() as db_session:
            area = (
                db_session.execute(select(Area).where(Area.id == area_id)).scalars().one_or_none()
            )

            if not area:
                raise ValidationError("Área no encontrada")

            # Check for associated tables
            table_count = (
                db_session.execute(
                    select(func.count(Table.id))
                    .where(Table.area_id == area_id)
                    .where(Table.is_active)
                ).scalar()
                or 0
            )

            if table_count > 0 and not force:
                raise ValidationError(
                    f"No se puede eliminar el área porque tiene {table_count} mesa(s) asociada(s). "
                    f"Elimine o reasigne las mesas primero."
                )

            if force and table_count > 0:
                # Hard delete: remove all associated tables
                db_session.execute(delete(Table).where(Table.area_id == area_id))
                logger.warning(
                    f"Force deleted {table_count} tables from area {area.name} (ID: {area_id})"
                )

            # Soft delete the area
            area.is_active = False
            db_session.commit()

            logger.info(f"Area deleted: {area.name} (ID: {area_id})")

            return {
                "success": True,
                "message": f"Área '{area.name}' eliminada correctamente",
                "deleted_tables": table_count if force else 0,
            }
