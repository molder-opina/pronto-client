"""
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, EmailStr, Field, validator

from shared.constants import FeedbackCategory, PaymentMethod
from shared.validation import validate_password, validate_role


class CreateEmployeeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str
    role: str = Field(default="staff")
    is_active: bool = Field(default=True)

    @validator("password")
    def validate_password_strength(cls, v):
        validate_password(v)
        return v

    @validator("role")
    def validate_role_value(cls, v):
        validate_role(v)
        return v


class UpdateEmployeeRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None

    @validator("password")
    def validate_password_strength(cls, v):
        if v is not None:
            validate_password(v)
        return v

    @validator("role")
    def validate_role_value(cls, v):
        if v is not None:
            validate_role(v)
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(..., min_length=1)

    @validator("email")
    def normalize_email(cls, v):
        """Normalize email to lowercase to ensure consistent authentication."""
        return v.strip().lower()


class CreateMenuItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    price: float = Field(..., gt=0)
    is_available: bool = Field(default=True)
    image_path: str | None = None
    category_id: int


class UpdateMenuItemRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    price: float | None = Field(None, gt=0)
    is_available: bool | None = None
    image_path: str | None = None


class OrderItemRequest(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1)


class CreateOrderRequest(BaseModel):
    customer: dict
    items: list[OrderItemRequest] = Field(..., min_items=1)
    notes: str | None = None
    table_number: str | None = None
    session_id: int | None = None


class ApplyTipRequest(BaseModel):
    tip_amount: float | None = Field(None, ge=0)
    tip_percentage: float | None = Field(None, ge=0, le=100)

    @validator("tip_percentage")
    def validate_tip_input(cls, v, values):
        if v is None and values.get("tip_amount") is None:
            raise ValueError("Debe proporcionar tip_amount o tip_percentage")
        return v


class FinalizePaymentRequest(BaseModel):
    payment_method: str
    tip_amount: float | None = Field(None, ge=0)
    tip_percentage: float | None = Field(None, ge=0, le=100)
    payment_reference: str | None = None
    customer_email: EmailStr | None = None
    customer_phone: str | None = None

    @validator("payment_method")
    def validate_payment_method(cls, v):
        if v not in {pm.value for pm in PaymentMethod}:
            allowed = ", ".join(pm.value for pm in PaymentMethod)
            raise ValueError(f"Método de pago inválido. Valores permitidos: {allowed}")
        return v


class UpdateContactRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None

    @validator("phone")
    def validate_at_least_one(cls, v, values):
        if v is None and values.get("email") is None:
            raise ValueError("Debe proporcionar email o phone")
        return v


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=200)


# Business Configuration Schemas
class BusinessInfoRequest(BaseModel):
    """Schema for creating/updating business information."""

    business_name: str = Field(..., min_length=1, max_length=200)
    address: str | None = None
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    email: EmailStr | None = None
    website: str | None = Field(None, max_length=200)
    logo_url: str | None = Field(None, max_length=500)
    description: str | None = None
    currency: str = Field(default="MXN", max_length=10)
    timezone: str = Field(default="America/Mexico_City", max_length=50)
    waiter_call_sound: str | None = Field(default="bell1.mp3", max_length=100)


class BusinessScheduleRequest(BaseModel):
    """Schema for creating/updating business schedule."""

    day_of_week: int = Field(..., ge=0, le=6)
    is_open: bool = Field(default=True)
    open_time: str | None = Field(None, pattern=r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    close_time: str | None = Field(None, pattern=r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    notes: str | None = Field(None, max_length=200)

    @validator("open_time", "close_time")
    def validate_time_when_open(cls, v, values):
        if values.get("is_open") and v is None:
            raise ValueError("open_time and close_time are required when is_open is True")
        return v


class SystemSettingRequest(BaseModel):
    """Schema for updating system settings."""

    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)
    value_type: str = Field(default="string", pattern=r"^(string|int|float|bool|json)$")
    description: str | None = Field(None, max_length=500)
    category: str = Field(default="general", max_length=50)


# Role Management Schemas
class RolePermissionRequest(BaseModel):
    """Schema for creating/updating role permissions."""

    resource_type: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=50)
    allowed: bool = Field(default=True)
    conditions: str | None = None


class CustomRoleRequest(BaseModel):
    """Schema for creating custom roles."""

    role_code: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_]*$")
    role_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(None, max_length=20, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    is_active: bool = Field(default=True)
    permissions: list[RolePermissionRequest] | None = None


class UpdateCustomRoleRequest(BaseModel):
    """Schema for updating custom roles."""

    role_name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(None, max_length=20, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    is_active: bool | None = None


# Feedback Schemas
class FeedbackRequest(BaseModel):
    """Schema for creating feedback."""

    session_id: int = Field(..., gt=0)
    employee_id: int | None = Field(None, gt=0)
    category: str
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    is_anonymous: bool = Field(default=False)

    @validator("category")
    def validate_category(cls, v):
        valid_categories = {cat.value for cat in FeedbackCategory}
        if v not in valid_categories:
            allowed = ", ".join(valid_categories)
            raise ValueError(f"Categoría inválida. Valores permitidos: {allowed}")
        return v


class BulkFeedbackRequest(BaseModel):
    """Schema for submitting multiple feedback entries at once."""

    session_id: int = Field(..., gt=0)
    employee_id: int | None = Field(None, gt=0)
    feedback_items: list[dict] = Field(..., min_items=1)
    is_anonymous: bool = Field(default=False)
