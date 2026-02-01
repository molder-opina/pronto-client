"""
SQLAlchemy ORM models shared by the pronto services.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Union

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .constants import ModificationStatus, OrderStatus
from .security import (
    decrypt_string,
    encrypt_string,
    hash_credentials,
    hash_identifier,
    verify_credentials,
)


class JSONBType(TypeDecorator):
    """
    Custom type that provides JSONB support for PostgreSQL
    and falls back to TEXT with JSON serialization for SQLite.

    This allows tests to run with SQLite while production uses PostgreSQL JSONB.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Use JSONB for PostgreSQL, Text for SQLite."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        else:
            # For SQLite and other dialects, use Text with JSON serialization
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        """Convert Python dict/list to JSON string for storage."""
        if value is None:
            return None
        if dialect.name == "postgresql":
            # PostgreSQL JSONB handles dicts/lists directly
            return value
        # SQLite: serialize to JSON string
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        """Convert JSON string back to Python dict/list."""
        if value is None:
            return None
        if dialect.name == "postgresql":
            # PostgreSQL JSONB already returns Python objects
            return value
        # SQLite: deserialize from JSON string
        if isinstance(value, str):
            return json.loads(value)
        return value

    @property
    def python_type(self):
        """Return the Python type this type coerces."""
        return object


# Use our custom JSONBType for all JSON columns
JSONB_TYPE = JSONBType()


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Customer(Base):
    __tablename__ = "pronto_customers"
    __table_args__ = (
        Index("ix_customer_email_hash", "email_hash"),
        Index("ix_customer_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    contact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    anon_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    physical_description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # For waiter notes to identify customer
    avatar: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Profile avatar filename (from predefined set)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="customer", cascade="all, delete-orphan"
    )

    @hybrid_property
    def name(self) -> str:
        value = decrypt_string(self.name_encrypted)
        return value or ""

    @name.setter
    def name(self, value: str) -> None:
        self.name_encrypted = encrypt_string(value or "")

    @hybrid_property
    def email(self) -> str:
        value = decrypt_string(self.email_encrypted)
        return value or ""

    @email.setter
    def email(self, value: str) -> None:
        raw_value = value or ""
        self.email_encrypted = encrypt_string(raw_value)
        self.email_hash = hash_identifier(raw_value)
        self._refresh_contact_hash(email=raw_value)

    @hybrid_property
    def phone(self) -> str | None:
        return decrypt_string(self.phone_encrypted)

    @phone.setter
    def phone(self, value: str | None) -> None:
        if value:
            self.phone_encrypted = encrypt_string(value)
        else:
            self.phone_encrypted = None
        self._refresh_contact_hash(phone=value)

    def _refresh_contact_hash(self, *, email: str | None = None, phone: str | None = None) -> None:
        current_email = email if email is not None else self.email
        current_phone = phone if phone is not None else (self.phone or "")
        self.contact_hash = hash_credentials(current_email or "", current_phone or "")

    @hybrid_property
    def is_anonymous(self) -> bool:
        return self.anon_id is not None and self.email_hash is None


class Employee(Base):
    __tablename__ = "pronto_employees"
    __table_args__ = (
        Index("ix_employee_email_hash", "email_hash"),
        Index("ix_employee_role_active", "role", "is_active"),
        Index("ix_employee_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    allow_scopes: Mapped[list[str] | None] = mapped_column(
        JSONB_TYPE, nullable=True
    )  # Native JSONB array
    auth_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="staff")
    additional_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    signed_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB_TYPE, nullable=True
    )  # Native JSONB object

    routes: Mapped[list[EmployeeRouteAccess]] = relationship(
        "EmployeeRouteAccess", back_populates="employee", cascade="all, delete-orphan"
    )

    @hybrid_property
    def name(self) -> str:
        value = decrypt_string(self.name_encrypted)
        return value or ""

    @name.setter
    def name(self, value: str) -> None:
        self.name_encrypted = encrypt_string(value or "")

    @hybrid_property
    def email(self) -> str:
        value = decrypt_string(self.email_encrypted)
        return value or ""

    @email.setter
    def email(self, value: str) -> None:
        raw_value = value or ""
        self.email_encrypted = encrypt_string(raw_value)
        self.email_hash = hash_identifier(raw_value)

    def set_password(self, password: str) -> None:
        if password is None:
            raise ValueError("password must not be None")
        self.auth_hash = hash_credentials(self.email, password)

    def verify_password(self, password: str) -> bool:
        return verify_credentials(self.email, password, self.auth_hash)

    def sign_in(self) -> None:
        """Mark employee as signed in"""
        now = datetime.utcnow()
        self.signed_in_at = now
        self.last_activity_at = now

    def sign_out(self) -> None:
        """Mark employee as signed out"""
        self.signed_in_at = None
        self.last_activity_at = None

    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity_at = datetime.utcnow()

    def is_signed_in(self, timeout_minutes: int = 5) -> bool:
        """
        Check if employee is currently signed in and active.

        Args:
            timeout_minutes: Minutes of inactivity before considering signed out

        Returns:
            True if signed in and active within timeout period
        """
        if not self.signed_in_at or not self.last_activity_at:
            return False

        from datetime import timedelta

        timeout = timedelta(minutes=timeout_minutes)
        now = datetime.utcnow()

        return (now - self.last_activity_at) <= timeout

    def get_preferences(self) -> dict[str, Any]:
        """Get employee preferences as dict - direct access to JSONB."""
        return self.preferences or {}

    def set_preferences(self, prefs: dict[str, Any]) -> None:
        """Set employee preferences from dict - direct assignment to JSONB."""
        self.preferences = prefs

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a single preference value."""
        return self.preferences.get(key) if self.preferences else default

    def set_preference(self, key: str, value: Any) -> None:
        """Set a single preference value."""
        if self.preferences is None:
            self.preferences = {}
        self.preferences[key] = value

    def get_scopes(self) -> list[str]:
        """Get allowed scopes as list - direct access to JSONB."""
        return self.allow_scopes or []

    def has_scope(self, scope: str) -> bool:
        """Check if employee has specific scope."""
        return scope in self.get_scopes()

    def add_scope(self, scope: str) -> None:
        """Add a scope to allowed scopes."""
        if self.allow_scopes is None:
            self.allow_scopes = []
        if scope not in self.allow_scopes:
            self.allow_scopes.append(scope)

    def remove_scope(self, scope: str) -> None:
        """Remove a scope from allowed scopes."""
        if self.allow_scopes and scope in self.allow_scopes:
            self.allow_scopes.remove(scope)


class EmployeePreference(Base):
    __tablename__ = "pronto_employee_preferences"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_employees.id", ondelete="CASCADE"), primary_key=True
    )
    preferences_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE, nullable=False, default=dict
    )  # Native JSONB for preferences
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped[Employee] = relationship("Employee", back_populates="preference_entry")


# Add relationship to Employee class
Employee.preference_entry = relationship(
    "EmployeePreference", uselist=False, back_populates="employee", cascade="all, delete-orphan"
)


class DiningSession(Base):
    __tablename__ = "pronto_dining_sessions"
    __table_args__ = (
        Index("ix_dining_session_status", "status"),
        Index("ix_dining_session_customer_status", "customer_id", "status"),
        Index("ix_dining_session_opened_at", "opened_at"),
        Index(
            "idx_dining_session_open_table",
            "table_id",
            unique=True,
            postgresql_where=text("status='open'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("pronto_customers.id"), nullable=False)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("pronto_tables.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    table_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # Deprecated, use table_id
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tip_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tip_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tip_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer: Mapped[Customer] = relationship("Customer")
    table: Mapped[Table | None] = relationship("Table", back_populates="sessions")
    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="session", cascade="all, delete-orphan"
    )

    def recompute_totals(self, db_session=None) -> None:
        from decimal import ROUND_HALF_UP

        from sqlalchemy import inspect

        # Get the session_id before any query to avoid detached instance errors
        # Access primary key which is always loaded
        session_id = inspect(self).identity[0] if inspect(self).identity else self.id

        # If no session provided, try to get it from the object's state
        if db_session is None:
            # Try to get session from object's state
            session_from_state = inspect(self).session
            if session_from_state:
                db_session = session_from_state

        # If we have a session, query orders explicitly to avoid lazy load issues
        if db_session and session_id:
            from sqlalchemy import select

            active_orders = list(
                db_session.execute(
                    select(Order).where(
                        Order.session_id == session_id,
                        Order.workflow_status != OrderStatus.CANCELLED.value,
                    )
                )
                .scalars()
                .all()
            )
        else:
            # Fallback to lazy loading if no session available
            active_orders = [
                order
                for order in self.orders
                if order.workflow_status != OrderStatus.CANCELLED.value
            ]

        # Calculate totals from orders
        subtotal = sum((Decimal(order.subtotal) for order in active_orders), Decimal("0")).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
        tax = sum((Decimal(order.tax_amount) for order in active_orders), Decimal("0")).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )

        # Get current tip (use 0 if not set yet)
        try:
            tip = Decimal(self.tip_amount or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)
        except Exception:
            tip = Decimal("0")

        # Update totals on self
        self.subtotal = subtotal
        self.tax_amount = tax
        self.total_amount = subtotal + tax + tip

    @hybrid_property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at


class RoutePermission(Base):
    __tablename__ = "pronto_route_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    app_target: Mapped[str] = mapped_column(String(32), nullable=False)

    employees: Mapped[list[EmployeeRouteAccess]] = relationship(
        "EmployeeRouteAccess", back_populates="permission", cascade="all, delete-orphan"
    )


class EmployeeRouteAccess(Base):
    __tablename__ = "pronto_employee_route_access"

    employee_id: Mapped[int] = mapped_column(ForeignKey("pronto_employees.id"), primary_key=True)
    route_permission_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_route_permissions.id"), primary_key=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee] = relationship("Employee", back_populates="routes")
    permission: Mapped[RoutePermission] = relationship(
        "RoutePermission", back_populates="employees"
    )


class MenuCategory(Base):
    __tablename__ = "pronto_menu_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    items: Mapped[list[MenuItem]] = relationship(
        "MenuItem", back_populates="category", cascade="all, delete-orphan"
    )


class MenuItem(Base):
    __tablename__ = "pronto_menu_items"
    __table_args__ = (CheckConstraint("price >= 0", name="chk_menu_items_price_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_path: Mapped[str] = mapped_column(String(255), nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_menu_categories.id"), nullable=False
    )
    preparation_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=15)
    # Recommended periods (breakfast: 6am-12pm, afternoon: 12pm-6pm, night: 6pm-12am)
    is_breakfast_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_afternoon_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_night_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Inventory tracking (optional)
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True, default=10)
    is_quick_serve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[MenuCategory] = relationship("MenuCategory", back_populates="items")
    order_items: Mapped[list[OrderItem]] = relationship("OrderItem", back_populates="menu_item")
    modifier_groups: Mapped[list[MenuItemModifierGroup]] = relationship(
        "MenuItemModifierGroup", back_populates="menu_item", cascade="all, delete-orphan"
    )
    day_period_assignments: Mapped[list[MenuItemDayPeriod]] = relationship(
        "MenuItemDayPeriod", back_populates="menu_item", cascade="all, delete-orphan"
    )
    schedules: Mapped[list[ProductSchedule]] = relationship(
        "ProductSchedule",
        back_populates="menu_item",
        cascade="all, delete-orphan",
        foreign_keys="ProductSchedule.menu_item_id",
    )


class ModifierGroup(Base):
    __tablename__ = "pronto_modifier_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    min_selection: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_selection: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    modifiers: Mapped[list[Modifier]] = relationship(
        "Modifier", back_populates="group", cascade="all, delete-orphan"
    )
    menu_items: Mapped[list[MenuItemModifierGroup]] = relationship(
        "MenuItemModifierGroup", back_populates="modifier_group", cascade="all, delete-orphan"
    )


class Modifier(Base):
    __tablename__ = "pronto_modifiers"
    __table_args__ = (
        CheckConstraint("price_adjustment >= 0", name="chk_modifiers_price_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("pronto_modifier_groups.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_adjustment: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    group: Mapped[ModifierGroup] = relationship("ModifierGroup", back_populates="modifiers")
    order_item_modifiers: Mapped[list[OrderItemModifier]] = relationship(
        "OrderItemModifier", back_populates="modifier"
    )


class MenuItemModifierGroup(Base):
    __tablename__ = "pronto_menu_item_modifier_groups"

    menu_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_menu_items.id"), primary_key=True)
    modifier_group_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_modifier_groups.id"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    menu_item: Mapped[MenuItem] = relationship("MenuItem", back_populates="modifier_groups")
    modifier_group: Mapped[ModifierGroup] = relationship(
        "ModifierGroup", back_populates="menu_items"
    )


class DayPeriod(Base):
    """
    Defines a named period of the day (e.g., morning, afternoon) that can be linked to menu logic.
    """

    __tablename__ = "pronto_day_periods"
    __table_args__ = (Index("ix_day_period_display_order", "display_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    menu_items: Mapped[list[MenuItemDayPeriod]] = relationship(
        "MenuItemDayPeriod", back_populates="period", cascade="all, delete-orphan"
    )


class MenuItemDayPeriod(Base):
    """
    Many-to-many link between menu items and configured day periods.
    """

    __tablename__ = "pronto_menu_item_day_periods"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "period_id", "tag_type", name="uq_menu_item_period_tag"),
        Index("ix_menu_item_period_menu", "menu_item_id"),
        Index("ix_menu_item_period_tag", "tag_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_menu_items.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("pronto_day_periods.id"), nullable=False)
    tag_type: Mapped[str] = mapped_column(String(32), nullable=False, default="recommendation")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    menu_item: Mapped[MenuItem] = relationship("MenuItem", back_populates="day_period_assignments")
    period: Mapped[DayPeriod] = relationship("DayPeriod", back_populates="menu_items")


class Order(Base):
    __tablename__ = "pronto_orders"
    __table_args__ = (
        Index("ix_order_workflow_status", "workflow_status"),
        Index("ix_order_status_created", "workflow_status", "created_at"),
        Index("ix_order_session_id", "session_id"),
        Index("ix_order_waiter_id", "waiter_id"),
        Index("ix_order_chef_id", "chef_id"),
        Index("ix_order_delivery_waiter_id", "delivery_waiter_id"),
        Index("ix_order_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("pronto_customers.id"), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("pronto_dining_sessions.id"), nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unpaid")
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB_TYPE, nullable=True
    )  # Native JSONB for payment metadata
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tip_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    waiter_id: Mapped[int | None] = mapped_column(ForeignKey("pronto_employees.id"), nullable=True)
    chef_id: Mapped[int | None] = mapped_column(ForeignKey("pronto_employees.id"), nullable=True)
    delivery_waiter_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    waiter_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    chef_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped[Customer] = relationship("Customer", back_populates="orders")
    session: Mapped[DiningSession] = relationship("DiningSession", back_populates="orders")
    waiter: Mapped[Employee | None] = relationship("Employee", foreign_keys=[waiter_id])
    chef: Mapped[Employee | None] = relationship("Employee", foreign_keys=[chef_id])
    delivery_waiter: Mapped[Employee | None] = relationship(
        "Employee", foreign_keys=[delivery_waiter_id]
    )
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    history: Mapped[list[OrderStatusHistory]] = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
    )

    def mark_status(self, status: str) -> None:
        # Validate status against enum
        try:
            # Ensure status is a valid enum value
            if status == "ATRASADO":
                raise ValueError("Estado inválido: 'ATRASADO'")

            # Check if status exists in OrderStatus enum values
            valid_statuses = {s.value for s in OrderStatus}
            if status not in valid_statuses:
                raise ValueError(f"Estado inválido: {status}")

        except ValueError as e:
            from shared.logging_config import get_logger

            logger = get_logger(__name__)
            logger.error(f"Attempted to set invalid status for order {self.id}: {e}")
            raise

        self.workflow_status = status
        self.updated_at = datetime.utcnow()
        self.history.append(OrderStatusHistory(status=status))

        # Emit realtime event for UI updates
        try:
            from shared.supabase.realtime import emit_order_status_change

            # Get table number safely
            table_number = None
            try:
                if hasattr(self, "session") and self.session:
                    table_number = self.session.table_number
            except Exception:  # nosec B110
                pass  # Ignore if session is not loaded

            emit_order_status_change(
                order_id=self.id,
                status=status,
                session_id=self.session_id,
                table_number=table_number,
            )
        except Exception as e:
            # Log but don't fail the status update if the realtime emit fails
            from shared.logging_config import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Failed to emit order status change for order {self.id}: {e}")


class OrderItem(Base):
    __tablename__ = "pronto_order_items"
    __table_args__ = (
        Index("ix_order_item_order_id", "order_id"),
        Index("ix_order_item_menu_item_id", "menu_item_id"),
        Index("ix_order_item_delivery_status", "is_fully_delivered", "delivered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("pronto_orders.id"), nullable=False)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_menu_items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Partial delivery tracking
    delivered_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_fully_delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )

    order: Mapped[Order] = relationship("Order", back_populates="items")
    menu_item: Mapped[MenuItem] = relationship("MenuItem", back_populates="order_items")
    delivered_by: Mapped[Employee | None] = relationship(
        "Employee", foreign_keys=[delivered_by_employee_id]
    )
    modifiers: Mapped[list[OrderItemModifier]] = relationship(
        "OrderItemModifier", back_populates="order_item", cascade="all, delete-orphan"
    )


class OrderItemModifier(Base):
    __tablename__ = "pronto_order_item_modifiers"
    __table_args__ = (
        Index("ix_order_item_modifier_item_id", "order_item_id"),
        Index("ix_order_item_modifier_modifier_id", "modifier_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_order_items.id"), nullable=False)
    modifier_id: Mapped[int] = mapped_column(ForeignKey("pronto_modifiers.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_adjustment: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    order_item: Mapped[OrderItem] = relationship("OrderItem", back_populates="modifiers")
    modifier: Mapped[Modifier] = relationship("Modifier", back_populates="order_item_modifiers")


class OrderStatusHistory(Base):
    __tablename__ = "pronto_order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("pronto_orders.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    order: Mapped[Order] = relationship("Order", back_populates="history")


class OrderStatusLabel(Base):
    """
    Editable status labels for the system console.
    """

    __tablename__ = "pronto_order_status_labels"
    __table_args__ = (Index("ix_order_status_label_key", "status_key", unique=True),)

    status_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    client_label: Mapped[str] = mapped_column(String(120), nullable=False)
    employee_label: Mapped[str] = mapped_column(String(120), nullable=False)
    admin_desc: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_emp_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    updated_by: Mapped[Employee | None] = relationship("Employee", foreign_keys=[updated_by_emp_id])


class OrderModification(Base):
    """
    Tracks modification requests for orders.
    - Customers can modify their orders before chef accepts (status must be 'new')
    - Waiters can modify orders anytime, but requires customer approval
    - Modifications are grouped as a package of changes (add items, remove items, update quantities)
    """

    __tablename__ = "pronto_order_modifications"
    __table_args__ = (
        Index("ix_order_modification_order", "order_id"),
        Index("ix_order_modification_status", "status"),
        Index("ix_order_modification_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("pronto_orders.id"), nullable=False)

    # Who initiated the modification
    initiated_by_role: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'customer' or 'waiter'
    initiated_by_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_customers.id"), nullable=True
    )
    initiated_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )

    # Status of the modification
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ModificationStatus.PENDING.value
    )

    # JSON structure containing the changes:
    # {
    #   "items_to_add": [{"menu_item_id": 1, "quantity": 2, "modifiers": [...], "special_instructions": "..."}],
    #   "items_to_remove": [order_item_id1, order_item_id2],
    #   "items_to_update": [{"order_item_id": 3, "quantity": 5}],
    #   "reason": "Customer changed their mind" (optional)
    # }
    changes_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB_TYPE, nullable=False, default=dict
    )  # Native JSONB for modification changes

    # Who reviewed the modification (only relevant for waiter-initiated changes)
    reviewed_by_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_customers.id"), nullable=True
    )
    reviewed_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    order: Mapped[Order] = relationship("Order", foreign_keys=[order_id])
    initiator_customer: Mapped[Customer | None] = relationship(
        "Customer", foreign_keys=[initiated_by_customer_id]
    )
    initiator_employee: Mapped[Employee | None] = relationship(
        "Employee", foreign_keys=[initiated_by_employee_id]
    )
    reviewer_customer: Mapped[Customer | None] = relationship(
        "Customer", foreign_keys=[reviewed_by_customer_id]
    )
    reviewer_employee: Mapped[Employee | None] = relationship(
        "Employee", foreign_keys=[reviewed_by_employee_id]
    )


class Notification(Base):
    __tablename__ = "pronto_notifications"
    __table_args__ = (
        Index("ix_notification_recipient_type_status", "recipient_type", "recipient_id", "status"),
        Index("ix_notification_created_at", "created_at"),
        Index("ix_notification_type", "notification_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "employee", "customer", "all_waiters", etc.
    recipient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Null for broadcast
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB_TYPE, nullable=True
    )  # Native JSONB for notification data
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unread"
    )  # unread, read, dismissed
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal"
    )  # low, normal, high, urgent
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Promotion(Base):
    __tablename__ = "pronto_promotions"
    __table_args__ = (
        CheckConstraint(
            "discount_percentage >= 0 AND discount_percentage <= 100",
            name="chk_promotions_discount_valid",
        ),
        CheckConstraint("discount_amount >= 0", name="chk_promotions_amount_positive"),
        Index("ix_promotion_active_dates", "is_active", "valid_from", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    discount_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_purchase_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    applies_to: Mapped[str] = mapped_column(
        String(32), nullable=False, default="products"
    )  # 'products', 'tags', 'package'
    applicable_tags: Mapped[list[str] | None] = mapped_column(JSONB_TYPE, nullable=True)
    applicable_products: Mapped[list[int] | None] = mapped_column(JSONB_TYPE, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    banner_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class DiscountCode(Base):
    __tablename__ = "pronto_discount_codes"
    __table_args__ = (
        CheckConstraint(
            "discount_percentage >= 0 AND discount_percentage <= 100",
            name="chk_discount_codes_discount_valid",
        ),
        CheckConstraint("discount_amount >= 0", name="chk_discount_codes_amount_positive"),
        CheckConstraint("usage_limit >= 0", name="chk_discount_codes_usage_limit_positive"),
        CheckConstraint("times_used >= 0", name="chk_discount_codes_times_used_positive"),
        Index("ix_discount_code", "code", unique=True),
        Index("ix_discount_active_dates", "is_active", "valid_from", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_type: Mapped[str] = mapped_column(String(32), nullable=False)
    discount_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_purchase_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applies_to: Mapped[str] = mapped_column(
        String(32), nullable=False, default="products"
    )  # 'products', 'tags', 'package'
    applicable_tags: Mapped[list[str] | None] = mapped_column(JSONB_TYPE, nullable=True)
    applicable_products: Mapped[list[int] | None] = mapped_column(JSONB_TYPE, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class BusinessConfig(Base):
    """
    Configuration parameters for the business that can be changed in real-time.
    """

    __tablename__ = "pronto_business_config"
    __table_args__ = (
        Index("ix_business_config_key", "config_key", unique=True),
        Index("ix_business_config_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    config_value: Mapped[Any] = mapped_column(
        JSONB_TYPE, nullable=False
    )  # Custom JSONBType for cross-dialect compatibility
    value_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="string"
    )  # string, int, float, bool, json
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # seconds, minutes, hours, percent, currency
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("pronto_employees.id"), nullable=True)


class Secret(Base):
    """Secret values stored in the database."""

    __tablename__ = "pronto_secrets"
    __table_args__ = (Index("ix_secret_key", "secret_key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    secret_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    secret_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class WaiterCall(Base):
    """
    Tracks waiter calls from customers with status and confirmation.
    """

    __tablename__ = "pronto_waiter_calls"
    __table_args__ = (
        Index("ix_waiter_call_session", "session_id"),
        Index("ix_waiter_call_status", "status"),
        Index("ix_waiter_call_created_at", "created_at"),
        Index("ix_waiter_call_confirmed_by", "confirmed_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_dining_sessions.id"), nullable=True
    )
    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending, confirmed, cancelled
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[DiningSession | None] = relationship("DiningSession", foreign_keys=[session_id])
    confirmer: Mapped[Employee | None] = relationship("Employee", foreign_keys=[confirmed_by])


class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class SupportTicket(Base):
    __tablename__ = "pronto_support_tickets"
    __table_args__ = (
        Index("ix_support_ticket_status", "status"),
        Index("ix_support_ticket_created_at", "created_at"),
        Index("ix_support_ticket_channel", "channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), default="client", nullable=False)
    name_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    description_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=SupportTicketStatus.OPEN.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @hybrid_property
    def name(self) -> str:
        return decrypt_string(self.name_encrypted) or ""

    @name.setter
    def name(self, value: str) -> None:
        self.name_encrypted = encrypt_string(value or "")

    @hybrid_property
    def email(self) -> str:
        return decrypt_string(self.email_encrypted) or ""

    @email.setter
    def email(self, value: str) -> None:
        self.email_encrypted = encrypt_string(value or "")

    @hybrid_property
    def description(self) -> str:
        return decrypt_string(self.description_encrypted) or ""

    @description.setter
    def description(self, value: str) -> None:
        self.description_encrypted = encrypt_string(value or "")


class Area(Base):
    """
    Represents areas/zones in the restaurant (e.g., Terraza, Interior, VIP, Bar).
    Each area can contain multiple tables and has visual configuration.
    """

    __tablename__ = "pronto_areas"
    __table_args__ = (
        Index("ix_area_name", "name", unique=True),
        Index("ix_area_prefix", "prefix", unique=True),
        Index("ix_area_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True
    )  # "Terraza", "Interior", "VIP"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(
        String(20), nullable=False, default="#ff6b35"
    )  # Color for UI
    prefix: Mapped[str] = mapped_column(
        String(10), nullable=False, unique=True
    )  # "T", "I", "V", "B" for table codes
    background_image: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Base64 encoded image from canvas
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    tables: Mapped[list[Table]] = relationship(
        "Table", back_populates="area", foreign_keys="Table.area_id"
    )


class Table(Base):
    """
    Represents physical tables in the restaurant with QR codes.
    Each table MUST be associated with an Area (FK constraint at DB level).
    """

    __tablename__ = "pronto_tables"
    __table_args__ = (
        Index("ix_table_number", "table_number", unique=True),
        Index("ix_table_qr_code", "qr_code", unique=True),
        Index("ix_table_status", "status"),
        Index("ix_table_area", "area_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    qr_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    area_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_areas.id"), nullable=False
    )  # REQUIRED: Each table MUST have an area
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="available"
    )  # available, occupied, reserved, maintenance
    position_x: Mapped[int | None] = mapped_column(Integer, nullable=True)  # For visual layout
    position_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shape: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="square"
    )  # square, round, rectangular
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    area: Mapped[Area] = relationship("Area", back_populates="tables", foreign_keys=[area_id])
    sessions: Mapped[list[DiningSession]] = relationship("DiningSession", back_populates="table")


class ProductSchedule(Base):
    """
    Defines availability schedules for menu items.
    """

    __tablename__ = "pronto_product_schedules"
    __table_args__ = (
        Index("ix_product_schedule_item", "menu_item_id"),
        Index("ix_product_schedule_active", "is_active"),
        Index(
            "ix_product_schedule_day_active", "day_of_week", "is_active"
        ),  # Para queries de disponibilidad
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_menu_items.id"), nullable=False)
    day_of_week: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=Monday, 6=Sunday, null=all days
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM format
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM format
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    menu_item: Mapped[MenuItem] = relationship("MenuItem", foreign_keys=[menu_item_id])


class SplitBill(Base):
    """
    Represents a bill split for a dining session.
    Allows multiple people to split the bill either equally or by specific items.
    """

    __tablename__ = "pronto_split_bills"
    __table_args__ = (
        Index("ix_split_bill_session", "session_id"),
        Index("ix_split_bill_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("pronto_dining_sessions.id"), nullable=False)
    split_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="by_items"
    )  # 'equal' or 'by_items'
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active"
    )  # 'active', 'completed', 'cancelled'
    number_of_people: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    session: Mapped[DiningSession] = relationship("DiningSession")
    people: Mapped[list[SplitBillPerson]] = relationship(
        "SplitBillPerson", back_populates="split_bill", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[SplitBillAssignment]] = relationship(
        "SplitBillAssignment", back_populates="split_bill", cascade="all, delete-orphan"
    )


class SplitBillPerson(Base):
    """
    Represents a person in a bill split.
    Each person has their own subtotal, tax, tip, and total.
    """

    __tablename__ = "pronto_split_bill_people"
    __table_args__ = (Index("ix_split_bill_person_split", "split_bill_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    split_bill_id: Mapped[int] = mapped_column(ForeignKey("pronto_split_bills.id"), nullable=False)
    person_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g., "Persona 1", "Juan", etc.
    person_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3, etc.

    # Financial fields
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tip_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    # Payment tracking
    payment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unpaid"
    )  # 'unpaid', 'paid'
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    split_bill: Mapped[SplitBill] = relationship("SplitBill", back_populates="people")
    assignments: Mapped[list[SplitBillAssignment]] = relationship(
        "SplitBillAssignment", back_populates="person", cascade="all, delete-orphan"
    )


class SplitBillAssignment(Base):
    """
    Assigns order items to specific people in a bill split.
    Each order item can be assigned to one or more people (for shared items).
    """

    __tablename__ = "pronto_split_bill_assignments"
    __table_args__ = (
        Index("ix_split_assignment_split", "split_bill_id"),
        Index("ix_split_assignment_person", "person_id"),
        Index("ix_split_assignment_item", "order_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    split_bill_id: Mapped[int] = mapped_column(ForeignKey("pronto_split_bills.id"), nullable=False)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_split_bill_people.id"), nullable=False
    )
    order_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_order_items.id"), nullable=False)

    # For shared items - what portion of the item this person pays for
    quantity_portion: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=1.0
    )  # e.g., 0.5 for half
    amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # The amount this person pays for this item

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    split_bill: Mapped[SplitBill] = relationship("SplitBill", back_populates="assignments")
    person: Mapped[SplitBillPerson] = relationship("SplitBillPerson", back_populates="assignments")
    order_item: Mapped[OrderItem] = relationship("OrderItem")


class BusinessInfo(Base):
    """
    Core business information: name, address, logo, contact details.
    This is a singleton table - only one row should exist.
    """

    __tablename__ = "pronto_business_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="MXN")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Mexico_City")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("pronto_employees.id"), nullable=True)


class BusinessSchedule(Base):
    """
    Business hours and closure days.
    Each row represents the schedule for a specific day of the week (0=Monday, 6=Sunday).
    """

    __tablename__ = "pronto_business_schedule"
    __table_args__ = (
        Index("ix_business_schedule_day", "day_of_week"),
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="check_day_of_week_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    open_time: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # Format: "HH:MM" (24-hour)
    close_time: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # Format: "HH:MM" (24-hour)
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CustomRole(Base):
    """
    Custom roles with configurable permissions.
    Allows creating business-specific roles beyond the default system roles.
    """

    __tablename__ = "pronto_custom_roles"
    __table_args__ = (
        Index("ix_custom_role_code", "role_code", unique=True),
        Index("ix_custom_role_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )  # e.g., "shift_manager"
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "Gerente de Turno"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Hex color for UI
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Icon name/class
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("pronto_employees.id"), nullable=True)

    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="custom_role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """
    Granular permissions for custom roles.
    Each permission grants access to specific features or actions.
    """

    __tablename__ = "pronto_role_permissions"
    __table_args__ = (
        Index("ix_role_permission_role", "custom_role_id"),
        Index("ix_role_permission_resource", "resource_type", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    custom_role_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_custom_roles.id"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "orders", "menu", "customers"
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "create", "read", "update", "delete", "approve"
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string for conditional logic

    custom_role: Mapped[CustomRole] = relationship("CustomRole", back_populates="permissions")


class Feedback(Base):
    """
    Customer feedback for rating waiters, food, and overall experience.
    Linked to dining sessions for context.
    """

    __tablename__ = "pronto_feedback"
    __table_args__ = (
        Index("ix_feedback_session", "session_id"),
        Index("ix_feedback_employee", "employee_id"),
        Index("ix_feedback_category", "category"),
        Index("ix_feedback_rating", "rating"),
        Index("ix_feedback_created_at", "created_at"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("pronto_dining_sessions.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_customers.id"), nullable=True
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )  # For waiter-specific feedback
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # Uses FeedbackCategory enum
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 stars
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped[DiningSession] = relationship("DiningSession")
    customer: Mapped[Customer | None] = relationship("Customer")
    employee: Mapped[Employee | None] = relationship("Employee")


class WaiterTableAssignment(Base):
    """
    Persistent waiter-table assignments for shift-based table management.
    Assignments remain active until explicitly unassigned (not session-based).
    """

    __tablename__ = "pronto_waiter_table_assignments"
    __table_args__ = (
        Index("ix_waiter_table_assignment_waiter", "waiter_id"),
        Index("ix_waiter_table_assignment_table", "table_id"),
        Index("ix_waiter_table_assignment_active", "is_active"),
        UniqueConstraint("waiter_id", "table_id", name="uq_waiter_table_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    waiter_id: Mapped[int] = mapped_column(ForeignKey("pronto_employees.id"), nullable=False)
    table_id: Mapped[int] = mapped_column(ForeignKey("pronto_tables.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    waiter: Mapped[Employee] = relationship("Employee", foreign_keys=[waiter_id])
    table: Mapped[Table] = relationship("Table", foreign_keys=[table_id])


class TableTransferRequest(Base):
    """
    Tracks table transfer requests between waiters.
    Supports optional transfer of existing orders associated with the table.
    """

    __tablename__ = "pronto_table_transfer_requests"
    __table_args__ = (
        Index("ix_table_transfer_from_waiter", "from_waiter_id"),
        Index("ix_table_transfer_to_waiter", "to_waiter_id"),
        Index("ix_table_transfer_table", "table_id"),
        Index("ix_table_transfer_status", "status"),
        Index("ix_table_transfer_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("pronto_tables.id"), nullable=False)
    from_waiter_id: Mapped[int] = mapped_column(ForeignKey("pronto_employees.id"), nullable=False)
    to_waiter_id: Mapped[int] = mapped_column(ForeignKey("pronto_employees.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending, accepted, rejected, cancelled
    transfer_orders: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Whether to transfer existing orders
    message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional message from requester
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )

    # Relationships
    table: Mapped[Table] = relationship("Table", foreign_keys=[table_id])
    from_waiter: Mapped[Employee] = relationship("Employee", foreign_keys=[from_waiter_id])
    to_waiter: Mapped[Employee] = relationship("Employee", foreign_keys=[to_waiter_id])
    resolver: Mapped[Employee | None] = relationship(
        "Employee", foreign_keys=[resolved_by_employee_id]
    )


class RealtimeEvent(Base):
    """
    Tabla para eventos en tiempo real usando Supabase en lugar de Redis.
    Reemplaza Redis Streams para mensajería de eventos.
    """

    __tablename__ = "pronto_realtime_events"
    __table_args__ = (
        Index("ix_realtime_event_type", "event_type"),
        Index("ix_realtime_event_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class RecommendationChangeLog(Base):
    """
    Historial de cambios en las recomendaciones de productos.
    Registra cuándo se agregan o eliminan productos de las recomendaciones.
    """

    __tablename__ = "pronto_recommendation_change_log"
    __table_args__ = (
        Index("ix_rec_log_menu_item", "menu_item_id"),
        Index("ix_rec_log_period", "period_key"),
        Index("ix_rec_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("pronto_menu_items.id"), nullable=False)
    period_key: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # breakfast, afternoon, night
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 'added' or 'removed'
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_employees.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    menu_item: Mapped[MenuItem] = relationship("MenuItem", backref="recommendation_logs")
    employee: Mapped[Employee | None] = relationship("Employee", backref="recommendation_changes")


class KeyboardShortcut(Base):
    """
    Configurable keyboard shortcuts for the customer app.
    Can be enabled/disabled and modified from the admin panel.
    """

    __tablename__ = "pronto_keyboard_shortcuts"
    __table_args__ = (
        Index("ix_shortcut_combo", "combo"),
        Index("ix_shortcut_enabled", "is_enabled"),
        UniqueConstraint("combo", name="uq_shortcut_combo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    combo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="General")
    callback_function: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prevent_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FeedbackQuestion(Base):
    """
    Configurable feedback questions for the customer feedback form.
    Can be customized from the admin panel.
    """

    __tablename__ = "pronto_feedback_questions"
    __table_args__ = (
        Index("ix_feedback_question_enabled", "is_enabled"),
        Index("ix_feedback_question_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False, default="rating")
    category: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_rating: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_rating: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FeedbackToken(Base):
    """
    Tokens for email-based feedback submissions.
    Allows sending feedback links to customers who didn't provide feedback immediately.
    """

    __tablename__ = "pronto_feedback_tokens"
    __table_args__ = (
        Index("ix_feedback_token_order", "order_id"),
        Index("ix_feedback_token_session", "session_id"),
        Index("ix_feedback_token_user", "user_id"),
        Index("ix_feedback_token_hash", "token_hash"),
        Index("ix_feedback_token_expires", "expires_at"),
        Index("ix_feedback_token_used", "used_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_orders.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_dining_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("pronto_customers.id", ondelete="CASCADE"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    order: Mapped[Order] = relationship("Order", backref="feedback_tokens")
    session: Mapped[DiningSession] = relationship("DiningSession", backref="feedback_tokens")
    user: Mapped[Customer | None] = relationship("Customer", backref="feedback_tokens")


class SystemRole(Base):
    __tablename__ = "pronto_system_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    permissions: Mapped[list[RolePermissionBinding]] = relationship(
        "RolePermissionBinding", back_populates="role", cascade="all, delete-orphan"
    )


class SystemPermission(Base):
    __tablename__ = "pronto_system_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    role_bindings: Mapped[list[RolePermissionBinding]] = relationship(
        "RolePermissionBinding", back_populates="permission"
    )


class RolePermissionBinding(Base):
    __tablename__ = "pronto_role_permission_bindings"

    role_id: Mapped[int] = mapped_column(ForeignKey("pronto_system_roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("pronto_system_permissions.id"), primary_key=True
    )

    role: Mapped[SystemRole] = relationship("SystemRole", back_populates="permissions")
    permission: Mapped[SystemPermission] = relationship(
        "SystemPermission", back_populates="role_bindings"
    )


class SuperAdminHandoffToken(Base):
    """
    Tokens de un solo uso para handoff de super_admin entre scopes.

    Permite que super_admin autenticado en /system pueda acceder
    a otros scopes sin re-escribir credenciales.
    """

    __tablename__ = "super_admin_handoff_tokens"
    __table_args__ = (
        Index("ix_handoff_token_hash", "token_hash"),
        Index("ix_handoff_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pronto_employees.id"), nullable=False
    )
    target_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship("Employee", backref="handoff_tokens")

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_used(self) -> bool:
        """Check if token has been used."""
        return self.used_at is not None

    @property
    def is_valid(self) -> bool:
        """Check if token is still valid."""
        return not self.is_expired and not self.is_used


class AuditLog(Base):
    """Audit log for security-sensitive operations."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_employee_id", "employee_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pronto_employees.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee | None] = relationship("Employee", backref="audit_logs")


class SystemSetting(Base):
    """
    System-wide configuration settings stored in the database.
    """

    __tablename__ = "pronto_system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
