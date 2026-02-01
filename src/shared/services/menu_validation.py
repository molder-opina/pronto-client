"""
Menu service validation module.
Contains comprehensive validation logic for menu items.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


class MenuValidationError(Exception):
    """Custom exception for menu validation errors."""

    pass


class MenuValidator:
    """Validates menu item data for create, update, and delete operations."""

    # Field length constraints
    NAME_MIN_LENGTH = 2
    NAME_MAX_LENGTH = 100
    DESCRIPTION_MAX_LENGTH = 500
    IMAGE_PATH_MAX_LENGTH = 255
    PREPARATION_TIME_MIN = 0
    PREPARATION_TIME_MAX = 300
    PRICE_MIN = Decimal("0.01")
    PRICE_MAX = Decimal("100000")

    # Business rules
    MAX_ACTIVE_ITEMS_PER_CATEGORY = 500

    def __init__(self, session=None):
        self.session = session
        self.errors: List[str] = []

    def validate_create(self, payload: Dict[str, Any]) -> None:
        """
        Validate menu item creation payload.
        Raises MenuValidationError if validation fails.
        """
        self._validate_required_fields(payload)
        self._validate_name(payload.get("name"))
        self._validate_price(payload.get("price"))
        self._validate_preparation_time(payload.get("preparation_time_minutes"))
        self._validate_description(payload.get("description"))
        self._validate_image_path(payload.get("image_path"))
        self._validate_category(payload.get("category"))
        self._validate_recommendation_periods(payload)

        if self.errors:
            raise MenuValidationError("; ".join(self.errors))

    def validate_update(self, item_id: int, payload: Dict[str, Any]) -> None:
        """
        Validate menu item update payload.
        Raises MenuValidationError if validation fails.
        """
        from shared.models import MenuItem
        from sqlalchemy import select

        if self.session:
            item = self.session.execute(
                select(MenuItem).where(MenuItem.id == item_id)
            ).scalar_one_or_none()

            if item is None:
                self.errors.append("Producto no encontrado")

        self._validate_name(payload.get("name"), allow_partial=True)
        self._validate_price(payload.get("price"), allow_partial=True)
        self._validate_preparation_time(payload.get("preparation_time_minutes"), allow_partial=True)
        self._validate_description(payload.get("description"))
        self._validate_image_path(payload.get("image_path"))
        self._validate_category(payload.get("category"))
        self._validate_recommendation_periods(payload)

        if self.errors:
            raise MenuValidationError("; ".join(self.errors))

    def validate_delete(self, item_id: int) -> None:
        """
        Validate menu item deletion.
        Raises MenuValidationError if validation fails.
        """
        from shared.models import MenuItem, OrderItem
        from sqlalchemy import select

        if self.session:
            # Check if item exists
            item = self.session.execute(
                select(MenuItem).where(MenuItem.id == item_id)
            ).scalar_one_or_none()

            if item is None:
                self.errors.append("Producto no encontrado")

            # Check if item has associated orders
            has_orders = self.session.execute(
                select(OrderItem.id).where(OrderItem.menu_item_id == item_id).limit(1)
            ).scalar_one_or_none()

            if has_orders:
                self.errors.append("No se puede eliminar: el producto tiene órdenes asociadas")

        if self.errors:
            raise MenuValidationError("; ".join(self.errors))

    def _validate_required_fields(self, payload: Dict[str, Any]) -> None:
        """Validate required fields are present and not empty."""
        required_fields = ["name", "price", "category"]

        for field in required_fields:
            value = payload.get(field)
            if value is None or value == "":
                self.errors.append(f"El campo '{field}' es obligatorio")
            elif isinstance(value, str) and value.strip() == "":
                self.errors.append(f"El campo '{field}' no puede estar vacío")

    def _validate_name(self, name: Any, allow_partial: bool = False) -> None:
        """Validate menu item name."""
        if name is None:
            if not allow_partial:
                self.errors.append("El nombre es obligatorio")
            return

        name_str = str(name).strip()

        # Check empty name
        if name_str == "":
            self.errors.append("El nombre no puede estar vacío o solo espacios")
            return

        # Check length
        if len(name_str) < self.NAME_MIN_LENGTH:
            self.errors.append(f"El nombre debe tener al menos {self.NAME_MIN_LENGTH} caracteres")

        if len(name_str) > self.NAME_MAX_LENGTH:
            self.errors.append(f"El nombre no puede exceder {self.NAME_MAX_LENGTH} caracteres")

    def _validate_price(self, price: Any, allow_partial: bool = False) -> None:
        """Validate menu item price."""
        if price is None:
            if not allow_partial:
                self.errors.append("El precio es obligatorio")
            return

        try:
            price_decimal = Decimal(str(price))

            # Check if price is positive
            if price_decimal < self.PRICE_MIN:
                self.errors.append(f"El precio debe ser mayor a {self.PRICE_MIN}")

            # Check maximum price
            if price_decimal > self.PRICE_MAX:
                self.errors.append(f"El precio no puede exceder {self.PRICE_MAX}")

            # Check precision (max 2 decimal places)
            if abs(price_decimal.as_tuple().exponent) > 2:
                self.errors.append("El precio no puede tener más de 2 decimales")

        except (ValueError, TypeError, Decimal.InvalidOperation):
            self.errors.append("El precio debe ser un número válido")

    def _validate_preparation_time(self, prep_time: Any, allow_partial: bool = False) -> None:
        """Validate preparation time in minutes."""
        if prep_time is None:
            return  # Optional field, no error if not provided

        try:
            prep_time_int = int(prep_time)

            if prep_time_int < self.PREPARATION_TIME_MIN:
                self.errors.append(f"El tiempo de preparación no puede ser negativo")

            if prep_time_int > self.PREPARATION_TIME_MAX:
                self.errors.append(
                    f"El tiempo de preparación no puede exceder {self.PREPARATION_TIME_MAX} minutos"
                )

        except (ValueError, TypeError):
            self.errors.append("El tiempo de preparación debe ser un número entero válido")

    def _validate_description(self, description: Any) -> None:
        """Validate menu item description."""
        if description is None or description == "":
            return  # Optional field, no error if not provided

        description_str = str(description).strip()

        if len(description_str) > self.DESCRIPTION_MAX_LENGTH:
            self.errors.append(
                f"La descripción no puede exceder {self.DESCRIPTION_MAX_LENGTH} caracteres"
            )

    def _validate_image_path(self, image_path: Any) -> None:
        """Validate image path."""
        if image_path is None or image_path == "":
            return  # Optional field, no error if not provided

        image_path_str = str(image_path).strip()

        if len(image_path_str) > self.IMAGE_PATH_MAX_LENGTH:
            self.errors.append(
                f"La ruta de la imagen no puede exceder {self.IMAGE_PATH_MAX_LENGTH} caracteres"
            )

    def _validate_category(self, category: Any) -> None:
        """Validate category."""
        if category is None or category == "":
            self.errors.append("La categoría es obligatoria")
            return

        category_str = str(category).strip()

        if category_str == "":
            self.errors.append("La categoría no puede estar vacía")

    def _validate_recommendation_periods(self, payload: Dict[str, Any]) -> None:
        """Validate recommendation periods."""
        period_fields = [
            "is_breakfast_recommended",
            "is_afternoon_recommended",
            "is_night_recommended",
        ]

        for field in period_fields:
            value = payload.get(field)
            if value is not None:
                if not isinstance(value, (bool, str)):
                    self.errors.append(f"El campo '{field}' debe ser booleano")
                elif isinstance(value, str):
                    normalized = value.strip().lower()
                    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
                        self.errors.append(f"El campo '{field}' debe ser true, false, 1 o 0")
