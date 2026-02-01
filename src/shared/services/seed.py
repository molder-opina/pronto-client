"""
Utilities to prepare default data for demos and local development.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

logger = logging.getLogger(__name__)

from shared.constants import FeedbackCategory
from shared.models import (
    Area,
    BusinessConfig,
    BusinessSchedule,
    Customer,
    DiningSession,
    Employee,
    EmployeeRouteAccess,
    Feedback,
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    Modifier,
    ModifierGroup,
    RolePermissionBinding,
    RoutePermission,
    SystemPermission,
    SystemRole,
    Table,
)
from shared.table_utils import build_table_code, derive_area_code, validate_table_code
from shared.validation import ValidationError

_SEED_LOCK_NAME = "pronto_ensure_seed_data"
_SEED_LOCK_TIMEOUT_SECONDS = 60


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _generate_qr_code(table_number: str, restaurant_slug: str) -> str:
    """Generate a unique QR code identifier for a table."""
    import hashlib
    import time

    unique_string = f"{restaurant_slug}-{table_number}-{int(time.time())}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:16]


# ==================== UPSERT HELPER FUNCTIONS ====================


def _get_or_create_category(
    session, name: str, description: str, display_order: int
) -> MenuCategory:
    """Find existing category by name or create new one. Updates fields if exists."""
    stmt = select(MenuCategory).where(MenuCategory.name == name)
    category = session.execute(stmt).scalars().one_or_none()

    if category:
        # Update existing category
        category.description = description
        category.display_order = display_order
    else:
        # Create new category
        category = MenuCategory(name=name, description=description, display_order=display_order)
        session.add(category)

    return category


def _get_or_create_menu_item(session, category: MenuCategory, **item_data) -> MenuItem:
    """Find existing menu item by name+category or create new one. Updates fields if exists."""
    name = item_data.get("name")
    stmt = select(MenuItem).where(MenuItem.name == name, MenuItem.category_id == category.id)
    item = session.execute(stmt).scalars().one_or_none()

    if item:
        # Update existing item
        item.description = item_data.get("description", item.description)
        item.price = item_data.get("price", item.price)
        item.image_path = item_data.get("image_path", item.image_path)
        item.preparation_time_minutes = item_data.get(
            "preparation_time_minutes", item.preparation_time_minutes
        )
        item.is_breakfast_recommended = item_data.get(
            "is_breakfast_recommended", item.is_breakfast_recommended
        )
        item.is_afternoon_recommended = item_data.get(
            "is_afternoon_recommended", item.is_afternoon_recommended
        )
        item.is_night_recommended = item_data.get("is_night_recommended", item.is_night_recommended)
        item.is_available = item_data.get("is_available", item.is_available)
        item.is_quick_serve = item_data.get("is_quick_serve", item.is_quick_serve)
    else:
        # Create new item
        item = MenuItem(category=category, **item_data)
        session.add(item)

    return item


def _get_or_create_modifier_group(session, **group_data) -> ModifierGroup:
    """Find existing modifier group by name or create new one. Updates fields if exists."""
    name = group_data.get("name")
    stmt = select(ModifierGroup).where(ModifierGroup.name == name)
    group = session.execute(stmt).scalars().one_or_none()

    if group:
        # Update existing group
        group.description = group_data.get("description", group.description)
        group.min_selection = group_data.get("min_selection", group.min_selection)
        group.max_selection = group_data.get("max_selection", group.max_selection)
        group.is_required = group_data.get("is_required", group.is_required)
        group.display_order = group_data.get("display_order", group.display_order)
    else:
        # Create new group
        group = ModifierGroup(**group_data)
        session.add(group)

    return group


def _get_or_create_modifier(
    session, group: ModifierGroup, name: str, price_adjustment, display_order: int
) -> Modifier:
    """Find existing modifier by name+group or create new one. Updates fields if exists."""
    stmt = select(Modifier).where(Modifier.name == name, Modifier.group_id == group.id)
    modifier = session.execute(stmt).scalars().one_or_none()

    if modifier:
        # Update existing modifier
        modifier.price_adjustment = price_adjustment
        modifier.display_order = display_order
    else:
        # Create new modifier
        modifier = Modifier(
            group=group, name=name, price_adjustment=price_adjustment, display_order=display_order
        )
        session.add(modifier)

    return modifier


def _get_or_create_area(
    session, name: str, description: str, prefix: str, color: str = "#ff6b35"
) -> Area:
    """Find existing area by name or create new one. Updates fields if exists."""
    stmt = select(Area).where(Area.name == name)
    area = session.execute(stmt).scalars().one_or_none()

    if area:
        # Update existing area
        area.description = description
        area.prefix = prefix
        area.color = color
    else:
        # Create new area
        area = Area(name=name, description=description, prefix=prefix, color=color, is_active=True)
        session.add(area)

    return area


def _get_or_create_table(
    session,
    table_number: str,
    area: Area,
    capacity: int,
    qr_code: str,
    status: str = "available",
) -> Table:
    """Find existing table by table_number or create new one. Updates fields if exists."""
    stmt = select(Table).where(Table.table_number == table_number)
    table = session.execute(stmt).scalars().one_or_none()

    if table:
        # Update existing table
        table.area_id = area.id
        table.capacity = capacity
        table.qr_code = qr_code
        table.status = status
    else:
        # Create new table
        table = Table(
            table_number=table_number,
            area_id=area.id,
            capacity=capacity,
            qr_code=qr_code,
            status=status,
            is_active=True,
        )
        session.add(table)

    return table


def _get_or_create_employee(
    session,
    email: str,
    name: str,
    role: str,
    default_password: str,
    *,
    force_password_reset: bool = False,
    additional_roles: str | None = None,
) -> Employee:
    """Get existing employee or create new one.

    Args:
        additional_roles: JSON string array of additional roles (e.g., '["cashier"]')
                         By default, waiters get '["cashier"]' to enable payment capability
    """
    from shared.security import hash_credentials, hash_identifier
    from shared.validation import validate_password

    email_hash = hash_identifier(email)
    employee = session.execute(
        select(Employee).where(Employee.email_hash == email_hash)
    ).scalar_one_or_none()

    # Set default additional_roles for waiters
    if additional_roles is None and role == "waiter":
        additional_roles = '["cashier"]'

    if employee:
        # Update existing
        employee.name = name
        employee.role = role
        employee.additional_roles = additional_roles
        if force_password_reset:
            validate_password(default_password)
            employee.auth_hash = hash_credentials(employee.email, default_password)
        # Set scopes based on role using add_scope
        import json as json_lib

        # Clear existing scopes by getting current and replacing
        current_scopes = employee.get_scopes()
        if role == "system":
            new_scopes = ["system", "admin", "waiter", "chef", "cashier"]
        elif role == "admin":
            new_scopes = ["admin", "waiter", "chef", "cashier"]
        elif role in ("waiter", "cashier"):
            new_scopes = ["waiter", "cashier"]
        elif role == "chef":
            new_scopes = ["chef"]
        elif role == "content_manager":
            new_scopes = ["admin"]
        else:
            new_scopes = []
        # Update allow_scopes column directly as JSON string
        employee.allow_scopes = json_lib.dumps(new_scopes)
    else:
        # Create new
        employee = Employee(role=role, additional_roles=additional_roles)
        employee.name = name
        employee.email = email
        validate_password(default_password)
        employee.auth_hash = hash_credentials(employee.email, default_password)
        # Set scopes based on role
        import json as json_lib

        if role == "system":
            new_scopes = ["system", "admin", "waiter", "chef", "cashier"]
        elif role == "admin":
            new_scopes = ["admin", "waiter", "chef", "cashier"]
        elif role in ("waiter", "cashier"):
            new_scopes = ["waiter", "cashier"]
        elif role == "chef":
            new_scopes = ["chef"]
        elif role == "content_manager":
            new_scopes = ["admin"]
        else:
            new_scopes = []
        employee.allow_scopes = json_lib.dumps(new_scopes)
        session.add(employee)

    return employee


def _assign_missing_employee_identity(session) -> int:
    """Fill name/email for employees missing identity data."""
    from shared.security import hash_credentials
    from shared.validation import validate_password

    seed_password = os.getenv("SEED_EMPLOYEE_PASSWORD", "ChangeMe!123")
    validate_password(seed_password)

    employees = session.execute(select(Employee)).scalars().all()
    used_emails = {e.email.lower() for e in employees if e.email}

    role_defaults = {
        "super_admin": ("Admin General", "admin"),
        "admin": ("Admin Roles", "admin.roles"),
        "admin": ("Admin", "admin"),
        "system": ("System", "system"),
        "waiter": ("Mesero", "waiter"),
        "chef": ("Chef", "chef"),
        "cashier": ("Cajero", "cashier"),
        "content_manager": ("Contenido", "contenido"),
    }

    def unique_email(base_local: str) -> tuple[str, int]:
        suffix = 1
        candidate = f"{base_local}@cafeteria.test"
        while candidate.lower() in used_emails:
            suffix += 1
            candidate = f"{base_local}{suffix}@cafeteria.test"
        used_emails.add(candidate.lower())
        return candidate, suffix

    updated = 0
    for employee in employees:
        current_name = employee.name
        current_email = employee.email
        if current_name and current_email:
            continue

        role = (employee.role or "").strip().lower()
        default_name, base_local = role_defaults.get(role, ("Empleado", "empleado"))

        if not current_email:
            new_email, suffix = unique_email(base_local)
            employee.email = new_email
            # Ensure login works for seeded identities.
            employee.auth_hash = hash_credentials(employee.email, seed_password)
            if not current_name:
                employee.name = default_name if suffix == 1 else f"{default_name} {suffix}"
            updated += 1
            continue

        if not current_name:
            employee.name = default_name
            updated += 1

    return updated


def load_seed_data(session) -> None:
    """Load/update all seed data using UPSERT logic. Always runs, does not check if data exists."""
    restaurant_slug = _slugify(os.getenv("RESTAURANT_NAME", "pronto"))
    reset_passwords = os.getenv("RESET_EMPLOYEE_PASSWORDS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    def asset(path: str) -> str:
        return f"/assets/{restaurant_slug}/{path}"

    # ==================== CATEGORIES ====================
    # Original 7 categories
    combos = _get_or_create_category(session, "Combos", "Combos listos para disfrutar", 1)
    burgers = _get_or_create_category(session, "Hamburguesas", "Opciones clásicas y gourmet", 2)
    pizzas = _get_or_create_category(session, "Pizzas", "Pizzas artesanales", 3)
    tacos = _get_or_create_category(session, "Tacos", "Tacos mexicanos auténticos", 4)
    ensaladas = _get_or_create_category(session, "Ensaladas", "Frescas y saludables", 5)
    bebidas = _get_or_create_category(session, "Bebidas", "Bebidas frías y calientes", 6)
    postres = _get_or_create_category(session, "Postres", "Cierra con algo dulce", 7)

    # Additional 5 categories
    desayunos = _get_or_create_category(session, "Desayunos", "Comienza el día con energía", 8)
    botanas = _get_or_create_category(session, "Botanas", "Aperitivos para compartir", 9)
    antojitos = _get_or_create_category(session, "Antojitos Mexicanos", "Lo mejor de México", 10)
    sopas = _get_or_create_category(session, "Sopas", "Sopas calientes y reconfortantes", 11)
    especialidades = _get_or_create_category(
        session, "Especialidades", "Platillos especiales de la casa", 12
    )

    session.flush()

    # ==================== MENU ITEMS ====================
    # Combos
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Familiar",
        description="4 hamburguesas, papas y bebidas.",
        price=Decimal("29.99"),
        image_path=asset("menu/combos_familiar.png"),
        preparation_time_minutes=30,
        is_afternoon_recommended=True,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Pareja",
        description="2 hamburguesas, 2 papas medianas y 2 bebidas.",
        price=Decimal("18.99"),
        image_path=asset("menu/combo_pareja.png"),
        preparation_time_minutes=25,
    )
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Individual",
        description="1 hamburguesa, papas pequeñas y bebida.",
        price=Decimal("10.99"),
        image_path=asset("menu/combo_individual.png"),
        preparation_time_minutes=20,
    )
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Pizza Grande",
        description="Pizza grande, papas fritas y 2 bebidas.",
        price=Decimal("24.99"),
        image_path=asset("menu/combo_pizza.png"),
        preparation_time_minutes=28,
    )
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Tacos Fiesta",
        description="6 tacos variados, guacamole y 2 bebidas.",
        price=Decimal("22.99"),
        image_path=asset("menu/combo_tacos.png"),
        preparation_time_minutes=25,
    )
    _get_or_create_menu_item(
        session,
        combos,
        name="Combo Ensalada Saludable",
        description="Ensalada grande, wrap de pollo y smoothie.",
        price=Decimal("16.99"),
        image_path=asset("menu/combo_ensalada.png"),
        preparation_time_minutes=18,
    )

    # Hamburguesas
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa Doble Queso",
        description="Doble carne y queso, pan artesanal.",
        price=Decimal("9.50"),
        image_path=asset("menu/hamburguesa_doble.png"),
        preparation_time_minutes=18,
        is_afternoon_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa Clásica",
        description="Carne de res, lechuga, tomate y cebolla.",
        price=Decimal("7.50"),
        image_path=asset("menu/hamburguesa_clasica.png"),
        preparation_time_minutes=15,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa BBQ Bacon",
        description="Carne, bacon, queso cheddar y salsa BBQ.",
        price=Decimal("10.50"),
        image_path=asset("menu/hamburguesa_bbq.png"),
        preparation_time_minutes=18,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa Vegetariana",
        description="Medallón de garbanzos, aguacate y vegetales.",
        price=Decimal("8.50"),
        image_path=asset("menu/hamburguesa_veggie.png"),
        preparation_time_minutes=16,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa Mexicana",
        description="Carne, jalapeños, guacamole y queso pepper jack.",
        price=Decimal("11.50"),
        image_path=asset("menu/hamburguesa_mexicana.png"),
        preparation_time_minutes=19,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa de Pollo Crispy",
        description="Pollo empanizado, lechuga, tomate y mayonesa.",
        price=Decimal("9.00"),
        image_path=asset("menu/hamburguesa_pollo.png"),
        preparation_time_minutes=17,
    )
    _get_or_create_menu_item(
        session,
        burgers,
        name="Hamburguesa Blue Cheese",
        description="Carne angus, queso azul, cebolla caramelizada.",
        price=Decimal("12.50"),
        image_path=asset("menu/hamburguesa_blue.png"),
        preparation_time_minutes=18,
    )

    # Pizzas
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Margherita",
        description="Tomate, mozzarella fresca y albahaca.",
        price=Decimal("11.99"),
        image_path=asset("menu/pizza_margherita.png"),
        preparation_time_minutes=22,
        is_afternoon_recommended=True,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Pepperoni",
        description="Salsa de tomate, mozzarella y pepperoni.",
        price=Decimal("13.99"),
        image_path=asset("menu/pizza_pepperoni.png"),
        preparation_time_minutes=22,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Cuatro Quesos",
        description="Mozzarella, gorgonzola, parmesano y provolone.",
        price=Decimal("14.99"),
        image_path=asset("menu/pizza_cuatro_quesos.png"),
        preparation_time_minutes=24,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Hawaiana",
        description="Jamón, piña y queso mozzarella.",
        price=Decimal("12.99"),
        image_path=asset("menu/pizza_hawaiana.png"),
        preparation_time_minutes=22,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Vegetariana",
        description="Tomate, champiñones, pimientos, cebolla y aceitunas.",
        price=Decimal("13.50"),
        image_path=asset("menu/pizza_vegetariana.png"),
        preparation_time_minutes=23,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza BBQ Chicken",
        description="Pollo, salsa BBQ, cebolla morada y cilantro.",
        price=Decimal("14.50"),
        image_path=asset("menu/pizza_bbq_chicken.png"),
        preparation_time_minutes=24,
    )
    _get_or_create_menu_item(
        session,
        pizzas,
        name="Pizza Carnívora",
        description="Pepperoni, salchicha, jamón y bacon.",
        price=Decimal("15.99"),
        image_path=asset("menu/pizza_carnivora.png"),
        preparation_time_minutes=25,
    )

    # Tacos
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos al Pastor",
        description="3 tacos con carne al pastor, piña y cilantro.",
        price=Decimal("8.99"),
        image_path=asset("menu/tacos_pastor.png"),
        preparation_time_minutes=12,
        is_afternoon_recommended=True,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos de Carnitas",
        description="3 tacos con carnitas de cerdo y cebolla.",
        price=Decimal("9.50"),
        image_path=asset("menu/tacos_carnitas.png"),
        preparation_time_minutes=13,
    )
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos de Pescado",
        description="3 tacos con pescado empanizado y col.",
        price=Decimal("10.50"),
        image_path=asset("menu/tacos_pescado.png"),
        preparation_time_minutes=14,
    )
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos de Pollo",
        description="3 tacos con pollo marinado y aguacate.",
        price=Decimal("8.50"),
        image_path=asset("menu/tacos_pollo.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos de Camarón",
        description="3 tacos con camarones al ajillo y col.",
        price=Decimal("12.50"),
        image_path=asset("menu/tacos_camaron.png"),
        preparation_time_minutes=15,
    )
    _get_or_create_menu_item(
        session,
        tacos,
        name="Tacos Veganos",
        description="3 tacos con setas, frijoles y vegetales.",
        price=Decimal("7.99"),
        image_path=asset("menu/tacos_veganos.png"),
        preparation_time_minutes=10,
    )

    # Ensaladas
    _get_or_create_menu_item(
        session,
        ensaladas,
        name="Ensalada César",
        description="Lechuga romana, pollo, crutones y parmesano.",
        price=Decimal("8.50"),
        image_path=asset("menu/ensalada_cesar.png"),
        preparation_time_minutes=8,
        is_breakfast_recommended=True,
        is_afternoon_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        ensaladas,
        name="Ensalada Mediterránea",
        description="Tomate, pepino, aceitunas, queso feta.",
        price=Decimal("9.50"),
        image_path=asset("menu/ensalada_mediterranea.png"),
        preparation_time_minutes=10,
        is_breakfast_recommended=True,
        is_afternoon_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        ensaladas,
        name="Ensalada de Pollo a la Parrilla",
        description="Pollo, lechuga, tomate cherry, maíz y aguacate.",
        price=Decimal("10.50"),
        image_path=asset("menu/ensalada_pollo.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        ensaladas,
        name="Ensalada Caprese",
        description="Tomate, mozzarella fresca, albahaca y balsámico.",
        price=Decimal("8.99"),
        image_path=asset("menu/ensalada_caprese.png"),
        preparation_time_minutes=7,
    )
    _get_or_create_menu_item(
        session,
        ensaladas,
        name="Ensalada de Quinoa",
        description="Quinoa, garbanzos, pepino, pimiento y limón.",
        price=Decimal("9.99"),
        image_path=asset("menu/ensalada_quinoa.png"),
        preparation_time_minutes=9,
    )

    # Bebidas
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Coca-Cola",
        description="Refresco de cola 500ml.",
        price=Decimal("2.50"),
        image_path=asset("menu/coca_cola.png"),
        preparation_time_minutes=2,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Agua Mineral",
        description="Agua mineral natural 500ml.",
        price=Decimal("1.50"),
        image_path=asset("menu/agua.png"),
        preparation_time_minutes=1,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Jugo de Naranja",
        description="Jugo natural recién exprimido.",
        price=Decimal("3.50"),
        image_path=asset("menu/jugo_naranja.png"),
        preparation_time_minutes=15,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Limonada Natural",
        description="Limonada fresca preparada al momento.",
        price=Decimal("3.00"),
        image_path=asset("menu/limonada.png"),
        preparation_time_minutes=15,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Cerveza Artesanal",
        description="Cerveza local 330ml.",
        price=Decimal("4.50"),
        image_path=asset("menu/cerveza.png"),
        preparation_time_minutes=2,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Café Americano",
        description="Café negro recién preparado.",
        price=Decimal("2.00"),
        image_path=asset("menu/cafe_americano.png"),
        preparation_time_minutes=4,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Café Latte",
        description="Espresso con leche vaporizada.",
        price=Decimal("3.50"),
        image_path=asset("menu/cafe_latte.png"),
        preparation_time_minutes=5,
        is_breakfast_recommended=True,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Té Helado",
        description="Té negro helado con limón 500ml.",
        price=Decimal("2.50"),
        image_path=asset("menu/te_helado.png"),
        preparation_time_minutes=3,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Smoothie de Frutas",
        description="Batido de frutas tropicales.",
        price=Decimal("4.50"),
        image_path=asset("menu/smoothie.png"),
        preparation_time_minutes=5,
        is_breakfast_recommended=True,
        is_afternoon_recommended=True,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Cerveza Nacional",
        description="Cerveza nacional 355ml.",
        price=Decimal("3.50"),
        image_path=asset("menu/cerveza_nacional.png"),
        preparation_time_minutes=2,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Agua de Horchata",
        description="Agua fresca de arroz con canela.",
        price=Decimal("2.99"),
        image_path=asset("menu/agua_horchata.png"),
        preparation_time_minutes=3,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Agua de Jamaica",
        description="Agua fresca de flor de Jamaica.",
        price=Decimal("2.99"),
        image_path=asset("menu/agua_jamaica.png"),
        preparation_time_minutes=3,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Agua de Tamarindo",
        description="Agua fresca de tamarindo natural.",
        price=Decimal("2.99"),
        image_path=asset("menu/agua_tamarindo.png"),
        preparation_time_minutes=3,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Malteada de Chocolate",
        description="Malteada cremosa de chocolate con crema batida.",
        price=Decimal("5.50"),
        image_path=asset("menu/malteada_chocolate.png"),
        preparation_time_minutes=6,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Malteada de Fresa",
        description="Malteada de fresa con crema batida.",
        price=Decimal("5.50"),
        image_path=asset("menu/malteada_fresa.png"),
        preparation_time_minutes=6,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Malteada de Vainilla",
        description="Clásica malteada de vainilla con crema.",
        price=Decimal("5.50"),
        image_path=asset("menu/malteada_vainilla.png"),
        preparation_time_minutes=6,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Frappe de Café",
        description="Café frío batido con hielo y crema.",
        price=Decimal("5.99"),
        image_path=asset("menu/frappe_cafe.png"),
        preparation_time_minutes=5,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Cappuccino",
        description="Espresso con espuma de leche y canela.",
        price=Decimal("4.00"),
        image_path=asset("menu/cappuccino.png"),
        preparation_time_minutes=5,
        is_breakfast_recommended=True,
        is_quick_serve=True,
    )
    _get_or_create_menu_item(
        session,
        bebidas,
        name="Michelada",
        description="Cerveza preparada con limón, sal y salsas.",
        price=Decimal("5.50"),
        image_path=asset("menu/michelada.png"),
        preparation_time_minutes=4,
        is_quick_serve=True,
    )

    for drink in bebidas.items:
        drink.is_quick_serve = True

    # Postres
    _get_or_create_menu_item(
        session,
        postres,
        name="Cheesecake Frutos Rojos",
        description="Porción individual con coulis casero.",
        price=Decimal("4.90"),
        image_path=asset("menu/cheesecake_rojo.png"),
        preparation_time_minutes=15,
        is_afternoon_recommended=True,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Brownie con Helado",
        description="Brownie de chocolate con helado de vainilla.",
        price=Decimal("5.50"),
        image_path=asset("menu/brownie_helado.png"),
        preparation_time_minutes=7,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Tiramisú",
        description="Postre italiano tradicional.",
        price=Decimal("5.90"),
        image_path=asset("menu/tiramisu.png"),
        preparation_time_minutes=5,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Helado Artesanal",
        description="3 bolas de helado a elegir.",
        price=Decimal("4.50"),
        image_path=asset("menu/helado.png"),
        preparation_time_minutes=4,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Flan Casero",
        description="Flan de huevo con caramelo líquido.",
        price=Decimal("4.00"),
        image_path=asset("menu/flan.png"),
        preparation_time_minutes=5,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Pastel de Chocolate",
        description="Rebanada de pastel de chocolate con ganache.",
        price=Decimal("5.50"),
        image_path=asset("menu/pastel_chocolate.png"),
        preparation_time_minutes=6,
    )
    _get_or_create_menu_item(
        session,
        postres,
        name="Churros con Chocolate",
        description="Churros recién hechos con chocolate caliente.",
        price=Decimal("4.50"),
        image_path=asset("menu/churros.png"),
        preparation_time_minutes=8,
    )

    # Desayunos
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Chilaquiles Rojos",
        description="Tortilla frita bañada en salsa roja, crema y queso.",
        price=Decimal("8.50"),
        image_path=asset("menu/chilaquiles_rojos.png"),
        preparation_time_minutes=15,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Chilaquiles Verdes",
        description="Tortilla frita bañada en salsa verde con pollo.",
        price=Decimal("9.50"),
        image_path=asset("menu/chilaquiles_verdes.png"),
        preparation_time_minutes=15,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Huevos Rancheros",
        description="Huevos estrellados sobre tortilla con salsa ranchera.",
        price=Decimal("7.50"),
        image_path=asset("menu/huevos_rancheros.png"),
        preparation_time_minutes=12,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Huevos con Jamón",
        description="Huevos revueltos con jamón, frijoles y tortillas.",
        price=Decimal("7.00"),
        image_path=asset("menu/huevos_jamon.png"),
        preparation_time_minutes=10,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Hotcakes con Miel",
        description="Stack de 3 hotcakes esponjosos con miel de maple.",
        price=Decimal("6.50"),
        image_path=asset("menu/hotcakes.png"),
        preparation_time_minutes=8,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Molletes",
        description="Bolillo con frijoles, queso gratinado y pico de gallo.",
        price=Decimal("6.00"),
        image_path=asset("menu/molletes.png"),
        preparation_time_minutes=10,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Omelette",
        description="Omelette de 3 huevos con queso, jamón y champiñones.",
        price=Decimal("8.00"),
        image_path=asset("menu/omelette.png"),
        preparation_time_minutes=12,
        is_breakfast_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        desayunos,
        name="Pan Francés",
        description="Rebanadas de pan con huevo, canela y azúcar glass.",
        price=Decimal("7.50"),
        image_path=asset("menu/pan_frances.png"),
        preparation_time_minutes=10,
        is_breakfast_recommended=True,
    )

    # Botanas
    _get_or_create_menu_item(
        session,
        botanas,
        name="Alitas BBQ",
        description="10 alitas de pollo con salsa BBQ y aderezo ranch.",
        price=Decimal("11.50"),
        image_path=asset("menu/alitas_bbq.png"),
        preparation_time_minutes=20,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Alitas Buffalo",
        description="10 alitas picantes estilo Buffalo con apio.",
        price=Decimal("11.50"),
        image_path=asset("menu/alitas_buffalo.png"),
        preparation_time_minutes=20,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Nachos Supreme",
        description="Totopos con queso, carne, guacamole y crema.",
        price=Decimal("10.50"),
        image_path=asset("menu/nachos.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Dedos de Queso",
        description="8 dedos de mozzarella empanizados con marinara.",
        price=Decimal("9.50"),
        image_path=asset("menu/dedos_queso.png"),
        preparation_time_minutes=10,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Aros de Cebolla",
        description="Aros de cebolla empanizados con salsa ranch.",
        price=Decimal("7.50"),
        image_path=asset("menu/aros_cebolla.png"),
        preparation_time_minutes=10,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Papas con Queso y Tocino",
        description="Papas fritas cubiertas con queso cheddar y tocino.",
        price=Decimal("8.99"),
        image_path=asset("menu/papas_queso_tocino.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Guacamole con Totopos",
        description="Guacamole fresco preparado al momento con totopos.",
        price=Decimal("7.99"),
        image_path=asset("menu/guacamole.png"),
        preparation_time_minutes=8,
    )
    _get_or_create_menu_item(
        session,
        botanas,
        name="Camarones al Coco",
        description="8 camarones empanizados con coco y salsa agridulce.",
        price=Decimal("13.50"),
        image_path=asset("menu/camarones_coco.png"),
        preparation_time_minutes=15,
    )

    # Antojitos Mexicanos
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Quesadillas de Pollo",
        description="Tortilla de harina con queso y pollo deshebrado.",
        price=Decimal("8.50"),
        image_path=asset("menu/quesadilla_pollo.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Quesadillas de Champiñones",
        description="Tortilla con queso Oaxaca y champiñones.",
        price=Decimal("7.99"),
        image_path=asset("menu/quesadilla_champinones.png"),
        preparation_time_minutes=10,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Torta Cubana",
        description="Torta con jamón, salchicha, huevo, queso y aguacate.",
        price=Decimal("9.50"),
        image_path=asset("menu/torta_cubana.png"),
        preparation_time_minutes=15,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Torta de Milanesa",
        description="Milanesa de pollo o res con frijoles y aguacate.",
        price=Decimal("8.99"),
        image_path=asset("menu/torta_milanesa.png"),
        preparation_time_minutes=14,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Sopes",
        description="3 sopes con frijoles, carne, lechuga y crema.",
        price=Decimal("9.99"),
        image_path=asset("menu/sopes.png"),
        preparation_time_minutes=16,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Flautas",
        description="4 flautas de pollo con crema, queso y guacamole.",
        price=Decimal("9.50"),
        image_path=asset("menu/flautas.png"),
        preparation_time_minutes=14,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Enchiladas Verdes",
        description="3 enchiladas bañadas en salsa verde con pollo.",
        price=Decimal("10.50"),
        image_path=asset("menu/enchiladas_verdes.png"),
        preparation_time_minutes=18,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Enchiladas Rojas",
        description="3 enchiladas en salsa roja con queso y crema.",
        price=Decimal("10.50"),
        image_path=asset("menu/enchiladas_rojas.png"),
        preparation_time_minutes=18,
    )
    _get_or_create_menu_item(
        session,
        antojitos,
        name="Gorditas",
        description="2 gorditas rellenas de chicharrón, queso o frijoles.",
        price=Decimal("8.50"),
        image_path=asset("menu/gorditas.png"),
        preparation_time_minutes=15,
    )

    # Sopas
    _get_or_create_menu_item(
        session,
        sopas,
        name="Sopa de Tortilla",
        description="Sopa de tomate con tiras de tortilla, aguacate y queso.",
        price=Decimal("7.50"),
        image_path=asset("menu/sopa_tortilla.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        sopas,
        name="Crema de Champiñones",
        description="Cremosa sopa de champiñones con crutones.",
        price=Decimal("7.99"),
        image_path=asset("menu/crema_champinones.png"),
        preparation_time_minutes=10,
    )
    _get_or_create_menu_item(
        session,
        sopas,
        name="Consomé de Pollo",
        description="Caldo de pollo con verduras y arroz.",
        price=Decimal("6.99"),
        image_path=asset("menu/consome_pollo.png"),
        preparation_time_minutes=10,
    )
    _get_or_create_menu_item(
        session,
        sopas,
        name="Minestrone",
        description="Sopa italiana de vegetales y pasta.",
        price=Decimal("7.50"),
        image_path=asset("menu/minestrone.png"),
        preparation_time_minutes=12,
    )
    _get_or_create_menu_item(
        session,
        sopas,
        name="Crema de Tomate",
        description="Suave crema de tomate con albahaca.",
        price=Decimal("6.99"),
        image_path=asset("menu/crema_tomate.png"),
        preparation_time_minutes=10,
    )

    # Especialidades
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Arrachera",
        description="300g de arrachera a la parrilla con guarnición.",
        price=Decimal("18.99"),
        image_path=asset("menu/arrachera.png"),
        preparation_time_minutes=25,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Filete de Pescado",
        description="Filete de pescado al mojo de ajo con arroz y verduras.",
        price=Decimal("16.99"),
        image_path=asset("menu/filete_pescado.png"),
        preparation_time_minutes=20,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Pollo a la Parrilla",
        description="Pechuga de pollo marinada con papas y ensalada.",
        price=Decimal("14.50"),
        image_path=asset("menu/pollo_parrilla.png"),
        preparation_time_minutes=22,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Fajitas Mixtas",
        description="Pollo y carne con pimientos, cebolla y tortillas.",
        price=Decimal("17.99"),
        image_path=asset("menu/fajitas_mixtas.png"),
        preparation_time_minutes=20,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Camarones al Ajillo",
        description="Camarones salteados en aceite de oliva y ajo.",
        price=Decimal("19.99"),
        image_path=asset("menu/camarones_ajillo.png"),
        preparation_time_minutes=18,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Molcajete",
        description="Carne asada, pollo, camarones y chorizo en molcajete.",
        price=Decimal("24.99"),
        image_path=asset("menu/molcajete.png"),
        preparation_time_minutes=30,
        is_night_recommended=True,
    )
    _get_or_create_menu_item(
        session,
        especialidades,
        name="Costillas BBQ",
        description="Costillas de cerdo bañadas en salsa BBQ.",
        price=Decimal("21.99"),
        image_path=asset("menu/costillas_bbq.png"),
        preparation_time_minutes=35,
        is_night_recommended=True,
    )

    session.flush()

    # ==================== MODIFIER GROUPS & MODIFIERS ====================
    # Grupo: Queso Extra
    queso_group = _get_or_create_modifier_group(
        session,
        name="Queso Extra",
        description="Agrega queso adicional",
        min_selection=0,
        max_selection=3,
        is_required=False,
        display_order=1,
    )
    session.flush()
    _get_or_create_modifier(session, queso_group, "Queso Cheddar", Decimal("1.50"), 1)
    _get_or_create_modifier(session, queso_group, "Queso Mozzarella", Decimal("1.50"), 2)
    _get_or_create_modifier(session, queso_group, "Queso Azul", Decimal("2.00"), 3)
    _get_or_create_modifier(session, queso_group, "Queso Pepper Jack", Decimal("1.75"), 4)

    # Grupo: Salsas
    salsas_group = _get_or_create_modifier_group(
        session,
        name="Salsas",
        description="Elige tus salsas favoritas",
        min_selection=0,
        max_selection=4,
        is_required=False,
        display_order=2,
    )
    session.flush()
    _get_or_create_modifier(session, salsas_group, "Salsa BBQ", Decimal("0.50"), 1)
    _get_or_create_modifier(session, salsas_group, "Salsa Ranch", Decimal("0.50"), 2)
    _get_or_create_modifier(session, salsas_group, "Salsa Picante", Decimal("0.50"), 3)
    _get_or_create_modifier(session, salsas_group, "Mayonesa", Decimal("0.30"), 4)
    _get_or_create_modifier(session, salsas_group, "Mostaza", Decimal("0.30"), 5)
    _get_or_create_modifier(session, salsas_group, "Ketchup", Decimal("0.30"), 6)
    _get_or_create_modifier(session, salsas_group, "Salsa Chipotle", Decimal("0.75"), 7)

    # Grupo: Proteínas Extra
    proteinas_group = _get_or_create_modifier_group(
        session,
        name="Proteínas Extra",
        description="Agrega proteína adicional",
        min_selection=0,
        max_selection=2,
        is_required=False,
        display_order=3,
    )
    session.flush()
    _get_or_create_modifier(session, proteinas_group, "Carne Extra", Decimal("3.00"), 1)
    _get_or_create_modifier(session, proteinas_group, "Pollo Extra", Decimal("2.50"), 2)
    _get_or_create_modifier(session, proteinas_group, "Bacon", Decimal("2.00"), 3)
    _get_or_create_modifier(session, proteinas_group, "Chorizo", Decimal("2.50"), 4)

    # Grupo: Vegetales
    vegetales_group = _get_or_create_modifier_group(
        session,
        name="Vegetales",
        description="Personaliza tus vegetales",
        min_selection=0,
        max_selection=10,
        is_required=False,
        display_order=4,
    )
    session.flush()
    _get_or_create_modifier(session, vegetales_group, "Lechuga", Decimal("0.00"), 1)
    _get_or_create_modifier(session, vegetales_group, "Tomate", Decimal("0.00"), 2)
    _get_or_create_modifier(session, vegetales_group, "Cebolla", Decimal("0.00"), 3)
    _get_or_create_modifier(session, vegetales_group, "Pepinillos", Decimal("0.00"), 4)
    _get_or_create_modifier(session, vegetales_group, "Jalapeños", Decimal("0.50"), 5)
    _get_or_create_modifier(session, vegetales_group, "Aguacate", Decimal("1.50"), 6)
    _get_or_create_modifier(session, vegetales_group, "Champiñones", Decimal("1.00"), 7)
    _get_or_create_modifier(session, vegetales_group, "Pimientos", Decimal("0.75"), 8)

    # Grupo: Tamaño de Papas
    papas_size_group = _get_or_create_modifier_group(
        session,
        name="Tamaño de Papas",
        description="Elige el tamaño de tus papas",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=5,
    )
    session.flush()
    _get_or_create_modifier(session, papas_size_group, "Pequeñas", Decimal("0.00"), 1)
    _get_or_create_modifier(session, papas_size_group, "Medianas", Decimal("1.50"), 2)
    _get_or_create_modifier(session, papas_size_group, "Grandes", Decimal("2.50"), 3)

    # Grupo: Tamaño de Bebida
    bebida_size_group = _get_or_create_modifier_group(
        session,
        name="Tamaño de Bebida",
        description="Elige el tamaño de tu bebida",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=6,
    )
    session.flush()
    _get_or_create_modifier(session, bebida_size_group, "Pequeña (300ml)", Decimal("0.00"), 1)
    _get_or_create_modifier(session, bebida_size_group, "Mediana (500ml)", Decimal("0.50"), 2)
    _get_or_create_modifier(session, bebida_size_group, "Grande (750ml)", Decimal("1.00"), 3)

    # Grupo: Punto de cocción
    coccion_group = _get_or_create_modifier_group(
        session,
        name="Punto de Cocción",
        description="¿Cómo quieres tu carne?",
        min_selection=0,
        max_selection=1,
        is_required=False,
        display_order=7,
    )
    session.flush()
    _get_or_create_modifier(session, coccion_group, "Poco cocida", Decimal("0.00"), 1)
    _get_or_create_modifier(session, coccion_group, "Término medio", Decimal("0.00"), 2)
    _get_or_create_modifier(session, coccion_group, "Bien cocida", Decimal("0.00"), 3)

    # Grupo: Tipo de Bebida (OBLIGATORIO para combos)
    bebida_combo_group = _get_or_create_modifier_group(
        session,
        name="Elige tu Bebida",
        description="Selecciona la bebida incluida en tu combo",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=10,
    )
    session.flush()
    _get_or_create_modifier(session, bebida_combo_group, "Coca-Cola", Decimal("0.00"), 1)
    _get_or_create_modifier(session, bebida_combo_group, "Coca-Cola Zero", Decimal("0.00"), 2)
    _get_or_create_modifier(session, bebida_combo_group, "Sprite", Decimal("0.00"), 3)
    _get_or_create_modifier(session, bebida_combo_group, "Fanta Naranja", Decimal("0.00"), 4)
    _get_or_create_modifier(session, bebida_combo_group, "Agua Mineral", Decimal("0.00"), 5)
    _get_or_create_modifier(session, bebida_combo_group, "Té Helado", Decimal("0.50"), 6)
    _get_or_create_modifier(session, bebida_combo_group, "Limonada", Decimal("0.50"), 7)
    _get_or_create_modifier(session, bebida_combo_group, "Jugo de Naranja", Decimal("1.00"), 8)

    # Grupo: Guarnición (OBLIGATORIO para combos)
    guarnicion_group = _get_or_create_modifier_group(
        session,
        name="Elige tu Guarnición",
        description="Selecciona la guarnición de tu combo",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=11,
    )
    session.flush()
    _get_or_create_modifier(session, guarnicion_group, "Papas Fritas Clásicas", Decimal("0.00"), 1)
    _get_or_create_modifier(session, guarnicion_group, "Papas Gajo", Decimal("0.50"), 2)
    _get_or_create_modifier(session, guarnicion_group, "Aros de Cebolla", Decimal("1.00"), 3)
    _get_or_create_modifier(session, guarnicion_group, "Ensalada Verde", Decimal("0.50"), 4)
    _get_or_create_modifier(session, guarnicion_group, "Puré de Papa", Decimal("0.75"), 5)
    _get_or_create_modifier(session, guarnicion_group, "Verduras al Vapor", Decimal("1.00"), 6)

    # Grupo: Aderezo (OBLIGATORIO - 2 opciones)
    aderezo_group = _get_or_create_modifier_group(
        session,
        name="Elige tus Aderezos",
        description="Selecciona hasta 2 aderezos incluidos",
        min_selection=1,
        max_selection=2,
        is_required=True,
        display_order=12,
    )
    session.flush()
    _get_or_create_modifier(session, aderezo_group, "Salsa Ranch", Decimal("0.00"), 1)
    _get_or_create_modifier(session, aderezo_group, "Salsa BBQ", Decimal("0.00"), 2)
    _get_or_create_modifier(session, aderezo_group, "Mostaza Miel", Decimal("0.00"), 3)
    _get_or_create_modifier(session, aderezo_group, "Salsa de Ajo", Decimal("0.00"), 4)
    _get_or_create_modifier(session, aderezo_group, "Salsa Tártara", Decimal("0.00"), 5)
    _get_or_create_modifier(session, aderezo_group, "Salsa Picante Buffalo", Decimal("0.00"), 6)
    _get_or_create_modifier(session, aderezo_group, "Mayonesa Chipotle", Decimal("0.00"), 7)

    # Grupo: Tipo de Pan (OBLIGATORIO para hamburguesas de combo)
    pan_group = _get_or_create_modifier_group(
        session,
        name="Tipo de Pan",
        description="Elige el pan para tu hamburguesa",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=13,
    )
    session.flush()
    _get_or_create_modifier(session, pan_group, "Pan Blanco Clásico", Decimal("0.00"), 1)
    _get_or_create_modifier(session, pan_group, "Pan Integral", Decimal("0.50"), 2)
    _get_or_create_modifier(session, pan_group, "Pan con Semillas", Decimal("0.75"), 3)
    _get_or_create_modifier(session, pan_group, "Pan Brioche", Decimal("1.00"), 4)

    # Grupo: Nivel de Picante (OBLIGATORIO para tacos)
    picante_group = _get_or_create_modifier_group(
        session,
        name="Nivel de Picante",
        description="¿Qué tan picante lo quieres?",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=14,
    )
    session.flush()
    _get_or_create_modifier(session, picante_group, "Sin Picante", Decimal("0.00"), 1)
    _get_or_create_modifier(session, picante_group, "Suave", Decimal("0.00"), 2)
    _get_or_create_modifier(session, picante_group, "Medio", Decimal("0.00"), 3)
    _get_or_create_modifier(session, picante_group, "Picante", Decimal("0.00"), 4)
    _get_or_create_modifier(session, picante_group, "Muy Picante", Decimal("0.00"), 5)

    # Grupo: Base de Pizza (OBLIGATORIO para pizzas)
    base_pizza_group = _get_or_create_modifier_group(
        session,
        name="Base de Pizza",
        description="Elige el tipo de masa",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=15,
    )
    session.flush()
    _get_or_create_modifier(session, base_pizza_group, "Masa Tradicional", Decimal("0.00"), 1)
    _get_or_create_modifier(session, base_pizza_group, "Masa Delgada", Decimal("0.00"), 2)
    _get_or_create_modifier(session, base_pizza_group, "Masa Integral", Decimal("1.00"), 3)
    _get_or_create_modifier(
        session, base_pizza_group, "Masa con Queso en Orilla", Decimal("2.50"), 4
    )

    # Grupo: Ingrediente Extra Pizza (OBLIGATORIO - mínimo 1)
    extra_pizza_group = _get_or_create_modifier_group(
        session,
        name="Ingredientes Extra",
        description="Elige al menos 1 ingrediente adicional",
        min_selection=1,
        max_selection=5,
        is_required=True,
        display_order=16,
    )
    session.flush()
    _get_or_create_modifier(session, extra_pizza_group, "Pepperoni Extra", Decimal("1.50"), 1)
    _get_or_create_modifier(session, extra_pizza_group, "Champiñones", Decimal("1.00"), 2)
    _get_or_create_modifier(session, extra_pizza_group, "Aceitunas Negras", Decimal("1.00"), 3)
    _get_or_create_modifier(session, extra_pizza_group, "Pimientos", Decimal("1.00"), 4)
    _get_or_create_modifier(session, extra_pizza_group, "Cebolla Morada", Decimal("0.75"), 5)
    _get_or_create_modifier(session, extra_pizza_group, "Jalapeños", Decimal("1.00"), 6)
    _get_or_create_modifier(session, extra_pizza_group, "Piña", Decimal("1.00"), 7)
    _get_or_create_modifier(session, extra_pizza_group, "Tocino", Decimal("2.00"), 8)

    # Grupo: Salsa de Ensalada (OBLIGATORIO para ensaladas)
    aderezo_ensalada_group = _get_or_create_modifier_group(
        session,
        name="Aderezo de Ensalada",
        description="Elige el aderezo para tu ensalada",
        min_selection=1,
        max_selection=1,
        is_required=True,
        display_order=17,
    )
    session.flush()
    _get_or_create_modifier(
        session, aderezo_ensalada_group, "Vinagreta Balsámica", Decimal("0.00"), 1
    )
    _get_or_create_modifier(session, aderezo_ensalada_group, "Aderezo César", Decimal("0.00"), 2)
    _get_or_create_modifier(session, aderezo_ensalada_group, "Ranch", Decimal("0.00"), 3)
    _get_or_create_modifier(
        session, aderezo_ensalada_group, "Aceite de Oliva y Limón", Decimal("0.00"), 4
    )
    _get_or_create_modifier(session, aderezo_ensalada_group, "Mostaza Miel", Decimal("0.00"), 5)

    # Grupo: Topping de Postre (OBLIGATORIO para postres)
    topping_postre_group = _get_or_create_modifier_group(
        session,
        name="Topping Extra",
        description="Agrega un topping a tu postre",
        min_selection=1,
        max_selection=2,
        is_required=True,
        display_order=18,
    )
    session.flush()
    _get_or_create_modifier(session, topping_postre_group, "Salsa de Chocolate", Decimal("0.50"), 1)
    _get_or_create_modifier(session, topping_postre_group, "Salsa de Caramelo", Decimal("0.50"), 2)
    _get_or_create_modifier(session, topping_postre_group, "Crema Batida", Decimal("0.75"), 3)
    _get_or_create_modifier(session, topping_postre_group, "Frutos Rojos", Decimal("1.00"), 4)
    _get_or_create_modifier(session, topping_postre_group, "Nueces Picadas", Decimal("1.00"), 5)
    _get_or_create_modifier(
        session, topping_postre_group, "Chispas de Chocolate", Decimal("0.75"), 6
    )

    session.flush()

    # ==================== MENU ITEM MODIFIER GROUP ASSOCIATIONS ====================
    # First, clear existing associations for items we're about to reassociate
    # (This ensures we don't create duplicates when running upsert multiple times)
    hamburguesas = (
        session.execute(
            select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Hamburguesas")
        )
        .scalars()
        .all()
    )

    bebidas_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Bebidas"))
        .scalars()
        .all()
    )

    combos_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Combos"))
        .scalars()
        .all()
    )

    tacos_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Tacos"))
        .scalars()
        .all()
    )

    pizzas_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Pizzas"))
        .scalars()
        .all()
    )

    ensaladas_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Ensaladas"))
        .scalars()
        .all()
    )

    postres_items = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Postres"))
        .scalars()
        .all()
    )

    # Delete existing associations to avoid duplicates
    for item in (
        hamburguesas
        + bebidas_items
        + combos_items
        + tacos_items
        + pizzas_items
        + ensaladas_items
        + postres_items
    ):
        session.execute(
            select(MenuItemModifierGroup).where(MenuItemModifierGroup.menu_item_id == item.id)
        )
        # Delete all existing associations for this item
        stmt = select(MenuItemModifierGroup).where(MenuItemModifierGroup.menu_item_id == item.id)
        existing_assocs = session.execute(stmt).scalars().all()
        for assoc in existing_assocs:
            session.delete(assoc)

    session.flush()

    # Now create associations
    # Asociar grupos OPCIONALES a hamburguesas
    for hamburguesa in hamburguesas:
        session.add(
            MenuItemModifierGroup(
                menu_item=hamburguesa, modifier_group=queso_group, display_order=1
            )
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=hamburguesa, modifier_group=salsas_group, display_order=2
            )
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=hamburguesa, modifier_group=proteinas_group, display_order=3
            )
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=hamburguesa, modifier_group=vegetales_group, display_order=4
            )
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=hamburguesa, modifier_group=coccion_group, display_order=5
            )
        )
        session.add(
            MenuItemModifierGroup(menu_item=hamburguesa, modifier_group=pan_group, display_order=6)
        )

    # Asociar tamaños a bebidas
    for bebida in bebidas_items:
        session.add(
            MenuItemModifierGroup(
                menu_item=bebida, modifier_group=bebida_size_group, display_order=1
            )
        )

    # Asociar grupos OBLIGATORIOS a combos
    for combo in combos_items:
        session.add(
            MenuItemModifierGroup(
                menu_item=combo, modifier_group=bebida_combo_group, display_order=1
            )
        )
        session.add(
            MenuItemModifierGroup(menu_item=combo, modifier_group=guarnicion_group, display_order=2)
        )
        session.add(
            MenuItemModifierGroup(menu_item=combo, modifier_group=aderezo_group, display_order=3)
        )
        # Algunos combos también permiten personalizar
        session.add(
            MenuItemModifierGroup(menu_item=combo, modifier_group=salsas_group, display_order=4)
        )

    # Asociar grupos OBLIGATORIOS a tacos
    for taco in tacos_items:
        session.add(
            MenuItemModifierGroup(menu_item=taco, modifier_group=picante_group, display_order=1)
        )
        session.add(
            MenuItemModifierGroup(menu_item=taco, modifier_group=salsas_group, display_order=2)
        )

    # Asociar grupos OBLIGATORIOS a pizzas
    for pizza in pizzas_items:
        session.add(
            MenuItemModifierGroup(menu_item=pizza, modifier_group=base_pizza_group, display_order=1)
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=pizza, modifier_group=extra_pizza_group, display_order=2
            )
        )

    # Asociar grupos OBLIGATORIOS a ensaladas
    for ensalada in ensaladas_items:
        session.add(
            MenuItemModifierGroup(
                menu_item=ensalada, modifier_group=aderezo_ensalada_group, display_order=1
            )
        )
        session.add(
            MenuItemModifierGroup(
                menu_item=ensalada, modifier_group=vegetales_group, display_order=2
            )
        )

    # Asociar grupos OBLIGATORIOS a postres
    for postre in postres_items:
        session.add(
            MenuItemModifierGroup(
                menu_item=postre, modifier_group=topping_postre_group, display_order=1
            )
        )

    session.flush()

    # ==================== EMPLOYEES ====================
    default_password = os.getenv("SEED_EMPLOYEE_PASSWORD", "ChangeMe!123")

    # Create/update employees
    super_admin = _get_or_create_employee(
        session,
        "admin@cafeteria.test",
        "Admin General",
        "system",
        default_password,
        force_password_reset=reset_passwords,
    )
    admin_roles = _get_or_create_employee(
        session,
        "admin.roles@cafeteria.test",
        "Admin Roles",
        "admin",
        default_password,
        force_password_reset=reset_passwords,
    )

    # Meseros
    waiter1 = _get_or_create_employee(
        session,
        "juan.mesero@cafeteria.test",
        "Juan",
        "waiter",
        default_password,
        force_password_reset=reset_passwords,
    )
    waiter2 = _get_or_create_employee(
        session,
        "maria.mesera@cafeteria.test",
        "Maria",
        "waiter",
        default_password,
        force_password_reset=reset_passwords,
    )
    waiter3 = _get_or_create_employee(
        session,
        "pedro.mesero@cafeteria.test",
        "Pedro",
        "waiter",
        default_password,
        force_password_reset=reset_passwords,
    )

    # Chefs
    chef1 = _get_or_create_employee(
        session,
        "carlos.chef@cafeteria.test",
        "Carlos",
        "chef",
        default_password,
        force_password_reset=reset_passwords,
    )
    chef2 = _get_or_create_employee(
        session,
        "ana.chef@cafeteria.test",
        "Ana",
        "chef",
        default_password,
        force_password_reset=reset_passwords,
    )

    # Cajeros
    cashier1 = _get_or_create_employee(
        session,
        "laura.cajera@cafeteria.test",
        "Laura",
        "cashier",
        default_password,
        force_password_reset=reset_passwords,
    )
    cashier2 = _get_or_create_employee(
        session,
        "roberto.cajero@cafeteria.test",
        "Roberto",
        "cashier",
        default_password,
        force_password_reset=reset_passwords,
    )

    # Content Manager
    content = _get_or_create_employee(
        session,
        "sofia.contenido@cafeteria.test",
        "Sofia",
        "content_manager",
        default_password,
        force_password_reset=reset_passwords,
    )

    session.flush()

    # Get all permissions
    permissions_map = {
        perm.code: perm for perm in session.execute(select(RoutePermission)).scalars().all()
    }

    # Delete existing employee permissions to avoid duplicates
    for emp in [
        super_admin,
        admin_roles,
        waiter1,
        waiter2,
        waiter3,
        chef1,
        chef2,
        cashier1,
        cashier2,
        content,
    ]:
        session.execute(
            select(EmployeeRouteAccess).where(EmployeeRouteAccess.employee_id == emp.id)
        )
        existing_perms = (
            session.execute(
                select(EmployeeRouteAccess).where(EmployeeRouteAccess.employee_id == emp.id)
            )
            .scalars()
            .all()
        )
        for perm in existing_perms:
            session.delete(perm)

    session.flush()

    # Super admin gets all permissions
    for perm in permissions_map.values():
        session.add(EmployeeRouteAccess(employee_id=super_admin.id, route_permission_id=perm.id))

    # Admin roles permissions
    if "admin-roles" in permissions_map:
        session.add(
            EmployeeRouteAccess(employee=admin_roles, permission=permissions_map["admin-roles"])
        )

    # Waiter permissions
    if "waiter-board" in permissions_map:
        for waiter in [waiter1, waiter2, waiter3]:
            session.add(
                EmployeeRouteAccess(employee=waiter, permission=permissions_map["waiter-board"])
            )

    # Chef permissions
    if "kitchen-board" in permissions_map:
        for chef in [chef1, chef2]:
            session.add(
                EmployeeRouteAccess(employee=chef, permission=permissions_map["kitchen-board"])
            )

    # Content manager permissions
    if "content-manager" in permissions_map:
        session.add(
            EmployeeRouteAccess(employee=content, permission=permissions_map["content-manager"])
        )

    session.flush()
    _assign_missing_employee_identity(session)

    # ==================== BUSINESS SCHEDULE ====================
    existing_schedules = session.execute(select(BusinessSchedule)).scalars().all()
    if not existing_schedules:
        schedules = []
        for day in range(7):  # 0=Monday to 6=Sunday
            schedules.append(
                BusinessSchedule(
                    day_of_week=day,
                    is_open=True,
                    open_time="00:00",
                    close_time="23:59",
                    notes="Abierto todo el día (Seed UPSERT)",
                )
            )
        session.add_all(schedules)
        session.flush()

    # ==================== AREAS ====================
    terraza = _get_or_create_area(
        session,
        name="Terraza",
        description="Área exterior con vista",
        prefix="T",
        color="#10b981",
    )
    salon = _get_or_create_area(
        session,
        name="Salón Principal",
        description="Área interior principal",
        prefix="M",
        color="#ff6b35",
    )
    vip = _get_or_create_area(
        session,
        name="VIP",
        description="Área privada",
        prefix="V",
        color="#8b5cf6",
    )
    session.flush()

    # ==================== TABLES ====================
    # Terraza tables (T1-T3)
    _get_or_create_table(session, "T1", terraza, capacity=4, qr_code="T1-QR-SEED")
    _get_or_create_table(session, "T2", terraza, capacity=4, qr_code="T2-QR-SEED")
    _get_or_create_table(session, "T3", terraza, capacity=6, qr_code="T3-QR-SEED")

    # Salón Principal tables (M1-M4)
    _get_or_create_table(session, "M1", salon, capacity=2, qr_code="M1-QR-SEED")
    _get_or_create_table(session, "M2", salon, capacity=4, qr_code="M2-QR-SEED")
    _get_or_create_table(session, "M3", salon, capacity=4, qr_code="M3-QR-SEED")
    _get_or_create_table(session, "M4", salon, capacity=6, qr_code="M4-QR-SEED")

    # VIP tables (V1)
    _get_or_create_table(session, "V1", vip, capacity=8, qr_code="V1-QR-SEED")

    session.flush()
    logger.info("[SEED] Areas and tables seeded successfully")


def _seed_legacy_extended_menu(session, asset, bebidas):
    """Populate the extended legacy menu set used when the database starts empty."""
    beverages = (
        session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Bebidas"))
        .scalars()
        .all()
    )
    for drink in beverages:
        drink.is_quick_serve = True
    # Crear nuevas categorías
    desayunos = MenuCategory(
        name="Desayunos", description="Comienza el día con energía", display_order=8
    )
    botanas = MenuCategory(name="Botanas", description="Aperitivos para compartir", display_order=9)
    antojitos = MenuCategory(
        name="Antojitos Mexicanos", description="Lo mejor de México", display_order=10
    )
    sopas = MenuCategory(
        name="Sopas", description="Sopas calientes y reconfortantes", display_order=11
    )
    especialidades = MenuCategory(
        name="Especialidades", description="Platillos especiales de la casa", display_order=12
    )
    session.add_all([desayunos, botanas, antojitos, sopas, especialidades])
    session.flush()

    # Agregar más productos
    session.add_all(
        [
            # Desayunos
            MenuItem(
                name="Chilaquiles Rojos",
                description="Tortilla frita bañada en salsa roja, crema y queso.",
                price=Decimal("8.50"),
                category=desayunos,
                image_path=asset("menu/chilaquiles_rojos.png"),
                preparation_time_minutes=15,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Chilaquiles Verdes",
                description="Tortilla frita bañada en salsa verde con pollo.",
                price=Decimal("9.50"),
                category=desayunos,
                image_path=asset("menu/chilaquiles_verdes.png"),
                preparation_time_minutes=15,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Huevos Rancheros",
                description="Huevos estrellados sobre tortilla con salsa ranchera.",
                price=Decimal("7.50"),
                category=desayunos,
                image_path=asset("menu/huevos_rancheros.png"),
                preparation_time_minutes=12,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Huevos con Jamón",
                description="Huevos revueltos con jamón, frijoles y tortillas.",
                price=Decimal("7.00"),
                category=desayunos,
                image_path=asset("menu/huevos_jamon.png"),
                preparation_time_minutes=10,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Hotcakes con Miel",
                description="Stack de 3 hotcakes esponjosos con miel de maple.",
                price=Decimal("6.50"),
                category=desayunos,
                image_path=asset("menu/hotcakes.png"),
                preparation_time_minutes=8,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Molletes",
                description="Bolillo con frijoles, queso gratinado y pico de gallo.",
                price=Decimal("6.00"),
                category=desayunos,
                image_path=asset("menu/molletes.png"),
                preparation_time_minutes=10,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Omelette",
                description="Omelette de 3 huevos con queso, jamón y champiñones.",
                price=Decimal("8.00"),
                category=desayunos,
                image_path=asset("menu/omelette.png"),
                preparation_time_minutes=12,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Pan Francés",
                description="Rebanadas de pan con huevo, canela y azúcar glass.",
                price=Decimal("7.50"),
                category=desayunos,
                image_path=asset("menu/pan_frances.png"),
                preparation_time_minutes=10,
                is_breakfast_recommended=True,
            ),
            # Botanas
            MenuItem(
                name="Alitas BBQ",
                description="10 alitas de pollo con salsa BBQ y aderezo ranch.",
                price=Decimal("11.50"),
                category=botanas,
                image_path=asset("menu/alitas_bbq.png"),
                preparation_time_minutes=20,
            ),
            MenuItem(
                name="Alitas Buffalo",
                description="10 alitas picantes estilo Buffalo con apio.",
                price=Decimal("11.50"),
                category=botanas,
                image_path=asset("menu/alitas_buffalo.png"),
                preparation_time_minutes=20,
            ),
            MenuItem(
                name="Nachos Supreme",
                description="Totopos con queso, carne, guacamole y crema.",
                price=Decimal("10.50"),
                category=botanas,
                image_path=asset("menu/nachos.png"),
                preparation_time_minutes=12,
            ),
            MenuItem(
                name="Dedos de Queso",
                description="8 dedos de mozzarella empanizados con marinara.",
                price=Decimal("9.50"),
                category=botanas,
                image_path=asset("menu/dedos_queso.png"),
                preparation_time_minutes=10,
            ),
            MenuItem(
                name="Aros de Cebolla",
                description="Aros de cebolla empanizados con salsa ranch.",
                price=Decimal("7.50"),
                category=botanas,
                image_path=asset("menu/aros_cebolla.png"),
                preparation_time_minutes=10,
            ),
            MenuItem(
                name="Papas con Queso y Tocino",
                description="Papas fritas cubiertas con queso cheddar y tocino.",
                price=Decimal("8.99"),
                category=botanas,
                image_path=asset("menu/papas_queso_tocino.png"),
                preparation_time_minutes=12,
            ),
            MenuItem(
                name="Guacamole con Totopos",
                description="Guacamole fresco preparado al momento con totopos.",
                price=Decimal("7.99"),
                category=botanas,
                image_path=asset("menu/guacamole.png"),
                preparation_time_minutes=8,
            ),
            MenuItem(
                name="Camarones al Coco",
                description="8 camarones empanizados con coco y salsa agridulce.",
                price=Decimal("13.50"),
                category=botanas,
                image_path=asset("menu/camarones_coco.png"),
                preparation_time_minutes=15,
            ),
            # Antojitos Mexicanos
            MenuItem(
                name="Quesadillas de Pollo",
                description="Tortilla de harina con queso y pollo deshebrado.",
                price=Decimal("8.50"),
                category=antojitos,
                image_path=asset("menu/quesadilla_pollo.png"),
                preparation_time_minutes=12,
            ),
            MenuItem(
                name="Quesadillas de Champiñones",
                description="Tortilla con queso Oaxaca y champiñones.",
                price=Decimal("7.99"),
                category=antojitos,
                image_path=asset("menu/quesadilla_champinones.png"),
                preparation_time_minutes=10,
            ),
            MenuItem(
                name="Torta Cubana",
                description="Torta con jamón, salchicha, huevo, queso y aguacate.",
                price=Decimal("9.50"),
                category=antojitos,
                image_path=asset("menu/torta_cubana.png"),
                preparation_time_minutes=15,
            ),
            MenuItem(
                name="Torta de Milanesa",
                description="Milanesa de pollo o res con frijoles y aguacate.",
                price=Decimal("8.99"),
                category=antojitos,
                image_path=asset("menu/torta_milanesa.png"),
                preparation_time_minutes=14,
            ),
            MenuItem(
                name="Sopes",
                description="3 sopes con frijoles, carne, lechuga y crema.",
                price=Decimal("9.99"),
                category=antojitos,
                image_path=asset("menu/sopes.png"),
                preparation_time_minutes=16,
            ),
            MenuItem(
                name="Flautas",
                description="4 flautas de pollo con crema, queso y guacamole.",
                price=Decimal("9.50"),
                category=antojitos,
                image_path=asset("menu/flautas.png"),
                preparation_time_minutes=14,
            ),
            MenuItem(
                name="Enchiladas Verdes",
                description="3 enchiladas bañadas en salsa verde con pollo.",
                price=Decimal("10.50"),
                category=antojitos,
                image_path=asset("menu/enchiladas_verdes.png"),
                preparation_time_minutes=18,
            ),
            MenuItem(
                name="Enchiladas Rojas",
                description="3 enchiladas en salsa roja con queso y crema.",
                price=Decimal("10.50"),
                category=antojitos,
                image_path=asset("menu/enchiladas_rojas.png"),
                preparation_time_minutes=18,
            ),
            MenuItem(
                name="Gorditas",
                description="2 gorditas rellenas de chicharrón, queso o frijoles.",
                price=Decimal("8.50"),
                category=antojitos,
                image_path=asset("menu/gorditas.png"),
                preparation_time_minutes=15,
            ),
            # Sopas
            MenuItem(
                name="Sopa de Tortilla",
                description="Sopa de tomate con tiras de tortilla, aguacate y queso.",
                price=Decimal("7.50"),
                category=sopas,
                image_path=asset("menu/sopa_tortilla.png"),
                preparation_time_minutes=12,
            ),
            MenuItem(
                name="Crema de Champiñones",
                description="Cremosa sopa de champiñones con crutones.",
                price=Decimal("7.99"),
                category=sopas,
                image_path=asset("menu/crema_champinones.png"),
                preparation_time_minutes=10,
            ),
            MenuItem(
                name="Consomé de Pollo",
                description="Caldo de pollo con verduras y arroz.",
                price=Decimal("6.99"),
                category=sopas,
                image_path=asset("menu/consome_pollo.png"),
                preparation_time_minutes=10,
            ),
            MenuItem(
                name="Minestrone",
                description="Sopa italiana de vegetales y pasta.",
                price=Decimal("7.50"),
                category=sopas,
                image_path=asset("menu/minestrone.png"),
                preparation_time_minutes=12,
            ),
            MenuItem(
                name="Crema de Tomate",
                description="Suave crema de tomate con albahaca.",
                price=Decimal("6.99"),
                category=sopas,
                image_path=asset("menu/crema_tomate.png"),
                preparation_time_minutes=10,
            ),
            # Especialidades
            MenuItem(
                name="Arrachera",
                description="300g de arrachera a la parrilla con guarnición.",
                price=Decimal("18.99"),
                category=especialidades,
                image_path=asset("menu/arrachera.png"),
                preparation_time_minutes=25,
                is_night_recommended=True,
            ),
            MenuItem(
                name="Filete de Pescado",
                description="Filete de pescado al mojo de ajo con arroz y verduras.",
                price=Decimal("16.99"),
                category=especialidades,
                image_path=asset("menu/filete_pescado.png"),
                preparation_time_minutes=20,
            ),
            MenuItem(
                name="Pollo a la Parrilla",
                description="Pechuga de pollo marinada con papas y ensalada.",
                price=Decimal("14.50"),
                category=especialidades,
                image_path=asset("menu/pollo_parrilla.png"),
                preparation_time_minutes=22,
            ),
            MenuItem(
                name="Fajitas Mixtas",
                description="Pollo y carne con pimientos, cebolla y tortillas.",
                price=Decimal("17.99"),
                category=especialidades,
                image_path=asset("menu/fajitas_mixtas.png"),
                preparation_time_minutes=20,
                is_night_recommended=True,
            ),
            MenuItem(
                name="Camarones al Ajillo",
                description="Camarones salteados en aceite de oliva y ajo.",
                price=Decimal("19.99"),
                category=especialidades,
                image_path=asset("menu/camarones_ajillo.png"),
                preparation_time_minutes=18,
            ),
            MenuItem(
                name="Molcajete",
                description="Carne asada, pollo, camarones y chorizo en molcajete.",
                price=Decimal("24.99"),
                category=especialidades,
                image_path=asset("menu/molcajete.png"),
                preparation_time_minutes=30,
                is_night_recommended=True,
            ),
            MenuItem(
                name="Costillas BBQ",
                description="Costillas de cerdo bañadas en salsa BBQ.",
                price=Decimal("21.99"),
                category=especialidades,
                image_path=asset("menu/costillas_bbq.png"),
                preparation_time_minutes=35,
                is_night_recommended=True,
            ),
            # Más Bebidas
            MenuItem(
                name="Agua de Horchata",
                description="Agua fresca de arroz con canela.",
                price=Decimal("2.99"),
                category=bebidas,
                image_path=asset("menu/agua_horchata.png"),
                preparation_time_minutes=3,
            ),
            MenuItem(
                name="Agua de Jamaica",
                description="Agua fresca de flor de Jamaica.",
                price=Decimal("2.99"),
                category=bebidas,
                image_path=asset("menu/agua_jamaica.png"),
                preparation_time_minutes=3,
            ),
            MenuItem(
                name="Agua de Tamarindo",
                description="Agua fresca de tamarindo natural.",
                price=Decimal("2.99"),
                category=bebidas,
                image_path=asset("menu/agua_tamarindo.png"),
                preparation_time_minutes=3,
            ),
            MenuItem(
                name="Malteada de Chocolate",
                description="Malteada cremosa de chocolate con crema batida.",
                price=Decimal("5.50"),
                category=bebidas,
                image_path=asset("menu/malteada_chocolate.png"),
                preparation_time_minutes=6,
            ),
            MenuItem(
                name="Malteada de Fresa",
                description="Malteada de fresa con crema batida.",
                price=Decimal("5.50"),
                category=bebidas,
                image_path=asset("menu/malteada_fresa.png"),
                preparation_time_minutes=6,
            ),
            MenuItem(
                name="Malteada de Vainilla",
                description="Clásica malteada de vainilla con crema.",
                price=Decimal("5.50"),
                category=bebidas,
                image_path=asset("menu/malteada_vainilla.png"),
                preparation_time_minutes=6,
            ),
            MenuItem(
                name="Frappe de Café",
                description="Café frío batido con hielo y crema.",
                price=Decimal("5.99"),
                category=bebidas,
                image_path=asset("menu/frappe_cafe.png"),
                preparation_time_minutes=5,
            ),
            MenuItem(
                name="Cappuccino",
                description="Espresso con espuma de leche y canela.",
                price=Decimal("4.00"),
                category=bebidas,
                image_path=asset("menu/cappuccino.png"),
                preparation_time_minutes=5,
                is_breakfast_recommended=True,
            ),
            MenuItem(
                name="Michelada",
                description="Cerveza preparada con limón, sal y salsas.",
                price=Decimal("5.50"),
                category=bebidas,
                image_path=asset("menu/michelada.png"),
                preparation_time_minutes=4,
            ),
        ]
    )
    session.flush()


def _ensure_seed_data_impl(session, restaurant_slug: str) -> None:
    categories = session.execute(select(MenuCategory)).scalars().all()
    if not categories:
        combos = MenuCategory(
            name="Combos", description="Combos listos para disfrutar", display_order=1
        )
        burgers = MenuCategory(
            name="Hamburguesas", description="Opciones clásicas y gourmet", display_order=2
        )
        pizzas = MenuCategory(name="Pizzas", description="Pizzas artesanales", display_order=3)
        tacos = MenuCategory(
            name="Tacos", description="Tacos mexicanos auténticos", display_order=4
        )
        ensaladas = MenuCategory(
            name="Ensaladas", description="Frescas y saludables", display_order=5
        )
        bebidas = MenuCategory(
            name="Bebidas", description="Bebidas frías y calientes", display_order=6
        )
        postres = MenuCategory(name="Postres", description="Cierra con algo dulce", display_order=7)
        session.add_all([combos, burgers, pizzas, tacos, ensaladas, bebidas, postres])
        session.flush()

        def asset(path: str) -> str:
            return f"/assets/{restaurant_slug}/{path}"

        session.add_all(
            [
                # Combos
                MenuItem(
                    name="Combo Familiar",
                    description="4 hamburguesas, papas y bebidas.",
                    price=Decimal("29.99"),
                    category=combos,
                    image_path=asset("menu/combos_familiar.png"),
                    preparation_time_minutes=30,
                    is_afternoon_recommended=True,
                    is_night_recommended=True,
                ),
                MenuItem(
                    name="Combo Pareja",
                    description="2 hamburguesas, 2 papas medianas y 2 bebidas.",
                    price=Decimal("18.99"),
                    category=combos,
                    image_path=asset("menu/combo_pareja.png"),
                    preparation_time_minutes=25,
                ),
                MenuItem(
                    name="Combo Individual",
                    description="1 hamburguesa, papas pequeñas y bebida.",
                    price=Decimal("10.99"),
                    category=combos,
                    image_path=asset("menu/combo_individual.png"),
                    preparation_time_minutes=20,
                ),
                # Hamburguesas
                MenuItem(
                    name="Hamburguesa Doble Queso",
                    description="Doble carne y queso, pan artesanal.",
                    price=Decimal("9.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_doble.png"),
                    preparation_time_minutes=18,
                    is_afternoon_recommended=True,
                ),
                MenuItem(
                    name="Hamburguesa Clásica",
                    description="Carne de res, lechuga, tomate y cebolla.",
                    price=Decimal("7.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_clasica.png"),
                    preparation_time_minutes=15,
                ),
                MenuItem(
                    name="Hamburguesa BBQ Bacon",
                    description="Carne, bacon, queso cheddar y salsa BBQ.",
                    price=Decimal("10.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_bbq.png"),
                    preparation_time_minutes=18,
                ),
                MenuItem(
                    name="Hamburguesa Vegetariana",
                    description="Medallón de garbanzos, aguacate y vegetales.",
                    price=Decimal("8.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_veggie.png"),
                    preparation_time_minutes=16,
                ),
                # Pizzas
                MenuItem(
                    name="Pizza Margherita",
                    description="Tomate, mozzarella fresca y albahaca.",
                    price=Decimal("11.99"),
                    category=pizzas,
                    image_path=asset("menu/pizza_margherita.png"),
                    preparation_time_minutes=22,
                    is_afternoon_recommended=True,
                    is_night_recommended=True,
                ),
                MenuItem(
                    name="Pizza Pepperoni",
                    description="Salsa de tomate, mozzarella y pepperoni.",
                    price=Decimal("13.99"),
                    category=pizzas,
                    image_path=asset("menu/pizza_pepperoni.png"),
                    preparation_time_minutes=22,
                ),
                MenuItem(
                    name="Pizza Cuatro Quesos",
                    description="Mozzarella, gorgonzola, parmesano y provolone.",
                    price=Decimal("14.99"),
                    category=pizzas,
                    image_path=asset("menu/pizza_cuatro_quesos.png"),
                    preparation_time_minutes=24,
                ),
                MenuItem(
                    name="Pizza Hawaiana",
                    description="Jamón, piña y queso mozzarella.",
                    price=Decimal("12.99"),
                    category=pizzas,
                    image_path=asset("menu/pizza_hawaiana.png"),
                    preparation_time_minutes=22,
                ),
                # Tacos
                MenuItem(
                    name="Tacos al Pastor",
                    description="3 tacos con carne al pastor, piña y cilantro.",
                    price=Decimal("8.99"),
                    category=tacos,
                    image_path=asset("menu/tacos_pastor.png"),
                    preparation_time_minutes=12,
                    is_afternoon_recommended=True,
                    is_night_recommended=True,
                ),
                MenuItem(
                    name="Tacos de Carnitas",
                    description="3 tacos con carnitas de cerdo y cebolla.",
                    price=Decimal("9.50"),
                    category=tacos,
                    image_path=asset("menu/tacos_carnitas.png"),
                    preparation_time_minutes=13,
                ),
                MenuItem(
                    name="Tacos de Pescado",
                    description="3 tacos con pescado empanizado y col.",
                    price=Decimal("10.50"),
                    category=tacos,
                    image_path=asset("menu/tacos_pescado.png"),
                    preparation_time_minutes=14,
                ),
                # Ensaladas
                MenuItem(
                    name="Ensalada César",
                    description="Lechuga romana, pollo, crutones y parmesano.",
                    price=Decimal("8.50"),
                    category=ensaladas,
                    image_path=asset("menu/ensalada_cesar.png"),
                    preparation_time_minutes=8,
                    is_breakfast_recommended=True,
                    is_afternoon_recommended=True,
                ),
                MenuItem(
                    name="Ensalada Mediterránea",
                    description="Tomate, pepino, aceitunas, queso feta.",
                    price=Decimal("9.50"),
                    category=ensaladas,
                    image_path=asset("menu/ensalada_mediterranea.png"),
                    preparation_time_minutes=10,
                    is_breakfast_recommended=True,
                    is_afternoon_recommended=True,
                ),
                # Bebidas
                MenuItem(
                    name="Coca-Cola",
                    description="Refresco de cola 500ml.",
                    price=Decimal("2.50"),
                    category=bebidas,
                    image_path=asset("menu/coca_cola.png"),
                    preparation_time_minutes=2,
                ),
                MenuItem(
                    name="Agua Mineral",
                    description="Agua mineral natural 500ml.",
                    price=Decimal("1.50"),
                    category=bebidas,
                    image_path=asset("menu/agua.png"),
                    preparation_time_minutes=1,
                ),
                MenuItem(
                    name="Jugo de Naranja",
                    description="Jugo natural recién exprimido.",
                    price=Decimal("3.50"),
                    category=bebidas,
                    image_path=asset("menu/jugo_naranja.png"),
                    preparation_time_minutes=15,
                ),
                MenuItem(
                    name="Limonada Natural",
                    description="Limonada fresca preparada al momento.",
                    price=Decimal("3.00"),
                    category=bebidas,
                    image_path=asset("menu/limonada.png"),
                    preparation_time_minutes=15,
                ),
                MenuItem(
                    name="Cerveza Artesanal",
                    description="Cerveza local 330ml.",
                    price=Decimal("4.50"),
                    category=bebidas,
                    image_path=asset("menu/cerveza.png"),
                    preparation_time_minutes=2,
                ),
                MenuItem(
                    name="Café Americano",
                    description="Café negro recién preparado.",
                    price=Decimal("2.00"),
                    category=bebidas,
                    image_path=asset("menu/cafe_americano.png"),
                    preparation_time_minutes=4,
                ),
                MenuItem(
                    name="Café Latte",
                    description="Espresso con leche vaporizada.",
                    price=Decimal("3.50"),
                    category=bebidas,
                    image_path=asset("menu/cafe_latte.png"),
                    preparation_time_minutes=5,
                    is_breakfast_recommended=True,
                ),
                # Postres
                MenuItem(
                    name="Cheesecake Frutos Rojos",
                    description="Porción individual con coulis casero.",
                    price=Decimal("4.90"),
                    category=postres,
                    image_path=asset("menu/cheesecake_rojo.png"),
                    preparation_time_minutes=15,
                    is_afternoon_recommended=True,
                    is_night_recommended=True,
                ),
                MenuItem(
                    name="Brownie con Helado",
                    description="Brownie de chocolate con helado de vainilla.",
                    price=Decimal("5.50"),
                    category=postres,
                    image_path=asset("menu/brownie_helado.png"),
                    preparation_time_minutes=7,
                ),
                MenuItem(
                    name="Tiramisú",
                    description="Postre italiano tradicional.",
                    price=Decimal("5.90"),
                    category=postres,
                    image_path=asset("menu/tiramisu.png"),
                    preparation_time_minutes=5,
                ),
                MenuItem(
                    name="Helado Artesanal",
                    description="3 bolas de helado a elegir.",
                    price=Decimal("4.50"),
                    category=postres,
                    image_path=asset("menu/helado.png"),
                    preparation_time_minutes=4,
                ),
                # Más Hamburguesas
                MenuItem(
                    name="Hamburguesa Mexicana",
                    description="Carne, jalapeños, guacamole y queso pepper jack.",
                    price=Decimal("11.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_mexicana.png"),
                    preparation_time_minutes=19,
                ),
                MenuItem(
                    name="Hamburguesa de Pollo Crispy",
                    description="Pollo empanizado, lechuga, tomate y mayonesa.",
                    price=Decimal("9.00"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_pollo.png"),
                    preparation_time_minutes=17,
                ),
                MenuItem(
                    name="Hamburguesa Blue Cheese",
                    description="Carne angus, queso azul, cebolla caramelizada.",
                    price=Decimal("12.50"),
                    category=burgers,
                    image_path=asset("menu/hamburguesa_blue.png"),
                    preparation_time_minutes=18,
                ),
                # Más Pizzas
                MenuItem(
                    name="Pizza Vegetariana",
                    description="Tomate, champiñones, pimientos, cebolla y aceitunas.",
                    price=Decimal("13.50"),
                    category=pizzas,
                    image_path=asset("menu/pizza_vegetariana.png"),
                    preparation_time_minutes=23,
                ),
                MenuItem(
                    name="Pizza BBQ Chicken",
                    description="Pollo, salsa BBQ, cebolla morada y cilantro.",
                    price=Decimal("14.50"),
                    category=pizzas,
                    image_path=asset("menu/pizza_bbq_chicken.png"),
                    preparation_time_minutes=24,
                ),
                MenuItem(
                    name="Pizza Carnívora",
                    description="Pepperoni, salchicha, jamón y bacon.",
                    price=Decimal("15.99"),
                    category=pizzas,
                    image_path=asset("menu/pizza_carnivora.png"),
                    preparation_time_minutes=25,
                ),
                # Más Tacos
                MenuItem(
                    name="Tacos de Pollo",
                    description="3 tacos con pollo marinado y aguacate.",
                    price=Decimal("8.50"),
                    category=tacos,
                    image_path=asset("menu/tacos_pollo.png"),
                    preparation_time_minutes=12,
                ),
                MenuItem(
                    name="Tacos de Camarón",
                    description="3 tacos con camarones al ajillo y col.",
                    price=Decimal("12.50"),
                    category=tacos,
                    image_path=asset("menu/tacos_camaron.png"),
                    preparation_time_minutes=15,
                ),
                MenuItem(
                    name="Tacos Veganos",
                    description="3 tacos con setas, frijoles y vegetales.",
                    price=Decimal("7.99"),
                    category=tacos,
                    image_path=asset("menu/tacos_veganos.png"),
                    preparation_time_minutes=10,
                ),
                # Más Ensaladas
                MenuItem(
                    name="Ensalada de Pollo a la Parrilla",
                    description="Pollo, lechuga, tomate cherry, maíz y aguacate.",
                    price=Decimal("10.50"),
                    category=ensaladas,
                    image_path=asset("menu/ensalada_pollo.png"),
                    preparation_time_minutes=12,
                ),
                MenuItem(
                    name="Ensalada Caprese",
                    description="Tomate, mozzarella fresca, albahaca y balsámico.",
                    price=Decimal("8.99"),
                    category=ensaladas,
                    image_path=asset("menu/ensalada_caprese.png"),
                    preparation_time_minutes=7,
                ),
                MenuItem(
                    name="Ensalada de Quinoa",
                    description="Quinoa, garbanzos, pepino, pimiento y limón.",
                    price=Decimal("9.99"),
                    category=ensaladas,
                    image_path=asset("menu/ensalada_quinoa.png"),
                    preparation_time_minutes=9,
                ),
                # Más Bebidas
                MenuItem(
                    name="Té Helado",
                    description="Té negro helado con limón 500ml.",
                    price=Decimal("2.50"),
                    category=bebidas,
                    image_path=asset("menu/te_helado.png"),
                    preparation_time_minutes=3,
                ),
                MenuItem(
                    name="Smoothie de Frutas",
                    description="Batido de frutas tropicales.",
                    price=Decimal("4.50"),
                    category=bebidas,
                    image_path=asset("menu/smoothie.png"),
                    preparation_time_minutes=5,
                    is_breakfast_recommended=True,
                    is_afternoon_recommended=True,
                ),
                MenuItem(
                    name="Cerveza Nacional",
                    description="Cerveza nacional 355ml.",
                    price=Decimal("3.50"),
                    category=bebidas,
                    image_path=asset("menu/cerveza_nacional.png"),
                    preparation_time_minutes=2,
                ),
                # Más Postres
                MenuItem(
                    name="Flan Casero",
                    description="Flan de huevo con caramelo líquido.",
                    price=Decimal("4.00"),
                    category=postres,
                    image_path=asset("menu/flan.png"),
                    preparation_time_minutes=5,
                ),
                MenuItem(
                    name="Pastel de Chocolate",
                    description="Rebanada de pastel de chocolate con ganache.",
                    price=Decimal("5.50"),
                    category=postres,
                    image_path=asset("menu/pastel_chocolate.png"),
                    preparation_time_minutes=6,
                ),
                MenuItem(
                    name="Churros con Chocolate",
                    description="Churros recién hechos con chocolate caliente.",
                    price=Decimal("4.50"),
                    category=postres,
                    image_path=asset("menu/churros.png"),
                    preparation_time_minutes=8,
                ),
                # Nuevos Combos
                MenuItem(
                    name="Combo Pizza Grande",
                    description="Pizza grande, papas fritas y 2 bebidas.",
                    price=Decimal("24.99"),
                    category=combos,
                    image_path=asset("menu/combo_pizza.png"),
                    preparation_time_minutes=28,
                ),
                MenuItem(
                    name="Combo Tacos Fiesta",
                    description="6 tacos variados, guacamole y 2 bebidas.",
                    price=Decimal("22.99"),
                    category=combos,
                    image_path=asset("menu/combo_tacos.png"),
                    preparation_time_minutes=25,
                ),
                MenuItem(
                    name="Combo Ensalada Saludable",
                    description="Ensalada grande, wrap de pollo y smoothie.",
                    price=Decimal("16.99"),
                    category=combos,
                    image_path=asset("menu/combo_ensalada.png"),
                    preparation_time_minutes=18,
                ),
            ]
        )
        session.flush()

        _seed_legacy_extended_menu(session, asset, bebidas)

    # Crear modifier groups (aditamentos, salsas, extras)
    modifier_groups = session.execute(select(ModifierGroup)).scalars().all()
    if not modifier_groups:
        # Grupo: Queso Extra
        queso_group = ModifierGroup(
            name="Queso Extra",
            description="Agrega queso adicional",
            min_selection=0,
            max_selection=3,
            is_required=False,
            display_order=1,
        )
        session.add(queso_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=queso_group,
                    name="Queso Cheddar",
                    price_adjustment=Decimal("1.50"),
                    display_order=1,
                ),
                Modifier(
                    group=queso_group,
                    name="Queso Mozzarella",
                    price_adjustment=Decimal("1.50"),
                    display_order=2,
                ),
                Modifier(
                    group=queso_group,
                    name="Queso Azul",
                    price_adjustment=Decimal("2.00"),
                    display_order=3,
                ),
                Modifier(
                    group=queso_group,
                    name="Queso Pepper Jack",
                    price_adjustment=Decimal("1.75"),
                    display_order=4,
                ),
            ]
        )

        # Grupo: Salsas
        salsas_group = ModifierGroup(
            name="Salsas",
            description="Elige tus salsas favoritas",
            min_selection=0,
            max_selection=4,
            is_required=False,
            display_order=2,
        )
        session.add(salsas_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=salsas_group,
                    name="Salsa BBQ",
                    price_adjustment=Decimal("0.50"),
                    display_order=1,
                ),
                Modifier(
                    group=salsas_group,
                    name="Salsa Ranch",
                    price_adjustment=Decimal("0.50"),
                    display_order=2,
                ),
                Modifier(
                    group=salsas_group,
                    name="Salsa Picante",
                    price_adjustment=Decimal("0.50"),
                    display_order=3,
                ),
                Modifier(
                    group=salsas_group,
                    name="Mayonesa",
                    price_adjustment=Decimal("0.30"),
                    display_order=4,
                ),
                Modifier(
                    group=salsas_group,
                    name="Mostaza",
                    price_adjustment=Decimal("0.30"),
                    display_order=5,
                ),
                Modifier(
                    group=salsas_group,
                    name="Ketchup",
                    price_adjustment=Decimal("0.30"),
                    display_order=6,
                ),
                Modifier(
                    group=salsas_group,
                    name="Salsa Chipotle",
                    price_adjustment=Decimal("0.75"),
                    display_order=7,
                ),
            ]
        )

        # Grupo: Proteínas Extra
        proteinas_group = ModifierGroup(
            name="Proteínas Extra",
            description="Agrega proteína adicional",
            min_selection=0,
            max_selection=2,
            is_required=False,
            display_order=3,
        )
        session.add(proteinas_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=proteinas_group,
                    name="Carne Extra",
                    price_adjustment=Decimal("3.00"),
                    display_order=1,
                ),
                Modifier(
                    group=proteinas_group,
                    name="Pollo Extra",
                    price_adjustment=Decimal("2.50"),
                    display_order=2,
                ),
                Modifier(
                    group=proteinas_group,
                    name="Bacon",
                    price_adjustment=Decimal("2.00"),
                    display_order=3,
                ),
                Modifier(
                    group=proteinas_group,
                    name="Chorizo",
                    price_adjustment=Decimal("2.50"),
                    display_order=4,
                ),
            ]
        )

        # Grupo: Vegetales
        vegetales_group = ModifierGroup(
            name="Vegetales",
            description="Personaliza tus vegetales",
            min_selection=0,
            max_selection=10,
            is_required=False,
            display_order=4,
        )
        session.add(vegetales_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=vegetales_group,
                    name="Lechuga",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Tomate",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Cebolla",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Pepinillos",
                    price_adjustment=Decimal("0.00"),
                    display_order=4,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Jalapeños",
                    price_adjustment=Decimal("0.50"),
                    display_order=5,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Aguacate",
                    price_adjustment=Decimal("1.50"),
                    display_order=6,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Champiñones",
                    price_adjustment=Decimal("1.00"),
                    display_order=7,
                ),
                Modifier(
                    group=vegetales_group,
                    name="Pimientos",
                    price_adjustment=Decimal("0.75"),
                    display_order=8,
                ),
            ]
        )

        # Grupo: Tamaño de Papas
        papas_size_group = ModifierGroup(
            name="Tamaño de Papas",
            description="Elige el tamaño de tus papas",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=5,
        )
        session.add(papas_size_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=papas_size_group,
                    name="Pequeñas",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=papas_size_group,
                    name="Medianas",
                    price_adjustment=Decimal("1.50"),
                    display_order=2,
                ),
                Modifier(
                    group=papas_size_group,
                    name="Grandes",
                    price_adjustment=Decimal("2.50"),
                    display_order=3,
                ),
            ]
        )

        # Grupo: Tamaño de Bebida
        bebida_size_group = ModifierGroup(
            name="Tamaño de Bebida",
            description="Elige el tamaño de tu bebida",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=6,
        )
        session.add(bebida_size_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=bebida_size_group,
                    name="Pequeña (300ml)",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=bebida_size_group,
                    name="Mediana (500ml)",
                    price_adjustment=Decimal("0.50"),
                    display_order=2,
                ),
                Modifier(
                    group=bebida_size_group,
                    name="Grande (750ml)",
                    price_adjustment=Decimal("1.00"),
                    display_order=3,
                ),
            ]
        )

        # Grupo: Punto de cocción (para carnes)
        coccion_group = ModifierGroup(
            name="Punto de Cocción",
            description="¿Cómo quieres tu carne?",
            min_selection=0,
            max_selection=1,
            is_required=False,
            display_order=7,
        )
        session.add(coccion_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=coccion_group,
                    name="Poco cocida",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=coccion_group,
                    name="Término medio",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=coccion_group,
                    name="Bien cocida",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
            ]
        )

        # ==================== ADITAMENTOS OBLIGATORIOS PARA COMBOS/PAQUETES ====================

        # Grupo: Tipo de Bebida (OBLIGATORIO para combos)
        bebida_combo_group = ModifierGroup(
            name="Elige tu Bebida",
            description="Selecciona la bebida incluida en tu combo",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=10,
        )
        session.add(bebida_combo_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=bebida_combo_group,
                    name="Coca-Cola",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Coca-Cola Zero",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Sprite",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Fanta Naranja",
                    price_adjustment=Decimal("0.00"),
                    display_order=4,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Agua Mineral",
                    price_adjustment=Decimal("0.00"),
                    display_order=5,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Té Helado",
                    price_adjustment=Decimal("0.50"),
                    display_order=6,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Limonada",
                    price_adjustment=Decimal("0.50"),
                    display_order=7,
                ),
                Modifier(
                    group=bebida_combo_group,
                    name="Jugo de Naranja",
                    price_adjustment=Decimal("1.00"),
                    display_order=8,
                ),
            ]
        )

        # Grupo: Guarnición (OBLIGATORIO para combos)
        guarnicion_group = ModifierGroup(
            name="Elige tu Guarnición",
            description="Selecciona la guarnición de tu combo",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=11,
        )
        session.add(guarnicion_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=guarnicion_group,
                    name="Papas Fritas Clásicas",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=guarnicion_group,
                    name="Papas Gajo",
                    price_adjustment=Decimal("0.50"),
                    display_order=2,
                ),
                Modifier(
                    group=guarnicion_group,
                    name="Aros de Cebolla",
                    price_adjustment=Decimal("1.00"),
                    display_order=3,
                ),
                Modifier(
                    group=guarnicion_group,
                    name="Ensalada Verde",
                    price_adjustment=Decimal("0.50"),
                    display_order=4,
                ),
                Modifier(
                    group=guarnicion_group,
                    name="Puré de Papa",
                    price_adjustment=Decimal("0.75"),
                    display_order=5,
                ),
                Modifier(
                    group=guarnicion_group,
                    name="Verduras al Vapor",
                    price_adjustment=Decimal("1.00"),
                    display_order=6,
                ),
            ]
        )

        # Grupo: Aderezo (OBLIGATORIO - 2 opciones)
        aderezo_group = ModifierGroup(
            name="Elige tus Aderezos",
            description="Selecciona hasta 2 aderezos incluidos",
            min_selection=1,
            max_selection=2,
            is_required=True,
            display_order=12,
        )
        session.add(aderezo_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=aderezo_group,
                    name="Salsa Ranch",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Salsa BBQ",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Mostaza Miel",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Salsa de Ajo",
                    price_adjustment=Decimal("0.00"),
                    display_order=4,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Salsa Tártara",
                    price_adjustment=Decimal("0.00"),
                    display_order=5,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Salsa Picante Buffalo",
                    price_adjustment=Decimal("0.00"),
                    display_order=6,
                ),
                Modifier(
                    group=aderezo_group,
                    name="Mayonesa Chipotle",
                    price_adjustment=Decimal("0.00"),
                    display_order=7,
                ),
            ]
        )

        # Grupo: Tipo de Pan (OBLIGATORIO para hamburguesas de combo)
        pan_group = ModifierGroup(
            name="Tipo de Pan",
            description="Elige el pan para tu hamburguesa",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=13,
        )
        session.add(pan_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=pan_group,
                    name="Pan Blanco Clásico",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=pan_group,
                    name="Pan Integral",
                    price_adjustment=Decimal("0.50"),
                    display_order=2,
                ),
                Modifier(
                    group=pan_group,
                    name="Pan con Semillas",
                    price_adjustment=Decimal("0.75"),
                    display_order=3,
                ),
                Modifier(
                    group=pan_group,
                    name="Pan Brioche",
                    price_adjustment=Decimal("1.00"),
                    display_order=4,
                ),
            ]
        )

        # Grupo: Nivel de Picante (OBLIGATORIO para tacos)
        picante_group = ModifierGroup(
            name="Nivel de Picante",
            description="¿Qué tan picante lo quieres?",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=14,
        )
        session.add(picante_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=picante_group,
                    name="Sin Picante",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=picante_group,
                    name="Suave",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=picante_group,
                    name="Medio",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
                Modifier(
                    group=picante_group,
                    name="Picante",
                    price_adjustment=Decimal("0.00"),
                    display_order=4,
                ),
                Modifier(
                    group=picante_group,
                    name="Muy Picante",
                    price_adjustment=Decimal("0.00"),
                    display_order=5,
                ),
            ]
        )

        # Grupo: Base de Pizza (OBLIGATORIO para pizzas personalizadas)
        base_pizza_group = ModifierGroup(
            name="Base de Pizza",
            description="Elige el tipo de masa",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=15,
        )
        session.add(base_pizza_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=base_pizza_group,
                    name="Masa Tradicional",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=base_pizza_group,
                    name="Masa Delgada",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=base_pizza_group,
                    name="Masa Integral",
                    price_adjustment=Decimal("1.00"),
                    display_order=3,
                ),
                Modifier(
                    group=base_pizza_group,
                    name="Masa con Queso en Orilla",
                    price_adjustment=Decimal("2.50"),
                    display_order=4,
                ),
            ]
        )

        # Grupo: Ingrediente Extra Pizza (OBLIGATORIO - mínimo 1)
        extra_pizza_group = ModifierGroup(
            name="Ingredientes Extra",
            description="Elige al menos 1 ingrediente adicional",
            min_selection=1,
            max_selection=5,
            is_required=True,
            display_order=16,
        )
        session.add(extra_pizza_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=extra_pizza_group,
                    name="Pepperoni Extra",
                    price_adjustment=Decimal("1.50"),
                    display_order=1,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Champiñones",
                    price_adjustment=Decimal("1.00"),
                    display_order=2,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Aceitunas Negras",
                    price_adjustment=Decimal("1.00"),
                    display_order=3,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Pimientos",
                    price_adjustment=Decimal("1.00"),
                    display_order=4,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Cebolla Morada",
                    price_adjustment=Decimal("0.75"),
                    display_order=5,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Jalapeños",
                    price_adjustment=Decimal("1.00"),
                    display_order=6,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Piña",
                    price_adjustment=Decimal("1.00"),
                    display_order=7,
                ),
                Modifier(
                    group=extra_pizza_group,
                    name="Tocino",
                    price_adjustment=Decimal("2.00"),
                    display_order=8,
                ),
            ]
        )

        # Grupo: Salsa de Ensalada (OBLIGATORIO para ensaladas)
        aderezo_ensalada_group = ModifierGroup(
            name="Aderezo de Ensalada",
            description="Elige el aderezo para tu ensalada",
            min_selection=1,
            max_selection=1,
            is_required=True,
            display_order=17,
        )
        session.add(aderezo_ensalada_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=aderezo_ensalada_group,
                    name="Vinagreta Balsámica",
                    price_adjustment=Decimal("0.00"),
                    display_order=1,
                ),
                Modifier(
                    group=aderezo_ensalada_group,
                    name="Aderezo César",
                    price_adjustment=Decimal("0.00"),
                    display_order=2,
                ),
                Modifier(
                    group=aderezo_ensalada_group,
                    name="Ranch",
                    price_adjustment=Decimal("0.00"),
                    display_order=3,
                ),
                Modifier(
                    group=aderezo_ensalada_group,
                    name="Aceite de Oliva y Limón",
                    price_adjustment=Decimal("0.00"),
                    display_order=4,
                ),
                Modifier(
                    group=aderezo_ensalada_group,
                    name="Mostaza Miel",
                    price_adjustment=Decimal("0.00"),
                    display_order=5,
                ),
            ]
        )

        # Grupo: Topping de Postre (OBLIGATORIO para postres)
        topping_postre_group = ModifierGroup(
            name="Topping Extra",
            description="Agrega un topping a tu postre",
            min_selection=1,
            max_selection=2,
            is_required=True,
            display_order=18,
        )
        session.add(topping_postre_group)
        session.flush()

        session.add_all(
            [
                Modifier(
                    group=topping_postre_group,
                    name="Salsa de Chocolate",
                    price_adjustment=Decimal("0.50"),
                    display_order=1,
                ),
                Modifier(
                    group=topping_postre_group,
                    name="Salsa de Caramelo",
                    price_adjustment=Decimal("0.50"),
                    display_order=2,
                ),
                Modifier(
                    group=topping_postre_group,
                    name="Crema Batida",
                    price_adjustment=Decimal("0.75"),
                    display_order=3,
                ),
                Modifier(
                    group=topping_postre_group,
                    name="Frutos Rojos",
                    price_adjustment=Decimal("1.00"),
                    display_order=4,
                ),
                Modifier(
                    group=topping_postre_group,
                    name="Nueces Picadas",
                    price_adjustment=Decimal("1.00"),
                    display_order=5,
                ),
                Modifier(
                    group=topping_postre_group,
                    name="Chispas de Chocolate",
                    price_adjustment=Decimal("0.75"),
                    display_order=6,
                ),
            ]
        )

        session.flush()

        # Asociar modifier groups con menu items
        # Obtener los items recién creados por categoría
        hamburguesas = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Hamburguesas")
            )
            .scalars()
            .all()
        )

        bebidas_items = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Bebidas")
            )
            .scalars()
            .all()
        )

        combos_items = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Combos")
            )
            .scalars()
            .all()
        )

        tacos_items = (
            session.execute(select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Tacos"))
            .scalars()
            .all()
        )

        pizzas_items = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Pizzas")
            )
            .scalars()
            .all()
        )

        ensaladas_items = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Ensaladas")
            )
            .scalars()
            .all()
        )

        postres_items = (
            session.execute(
                select(MenuItem).join(MenuCategory).where(MenuCategory.name == "Postres")
            )
            .scalars()
            .all()
        )

        # Asociar grupos OPCIONALES a hamburguesas
        for hamburguesa in hamburguesas:
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=queso_group, display_order=1
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=salsas_group, display_order=2
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=proteinas_group, display_order=3
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=vegetales_group, display_order=4
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=coccion_group, display_order=5
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=hamburguesa, modifier_group=pan_group, display_order=6
                )
            )

        # Asociar tamaños a bebidas
        for bebida in bebidas_items:
            session.add(
                MenuItemModifierGroup(
                    menu_item=bebida, modifier_group=bebida_size_group, display_order=1
                )
            )

        # Asociar grupos OBLIGATORIOS a combos
        for combo in combos_items:
            session.add(
                MenuItemModifierGroup(
                    menu_item=combo, modifier_group=bebida_combo_group, display_order=1
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=combo, modifier_group=guarnicion_group, display_order=2
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=combo, modifier_group=aderezo_group, display_order=3
                )
            )
            # Algunos combos también permiten personalizar
            session.add(
                MenuItemModifierGroup(menu_item=combo, modifier_group=salsas_group, display_order=4)
            )

        # Asociar grupos OBLIGATORIOS a tacos
        for taco in tacos_items:
            session.add(
                MenuItemModifierGroup(menu_item=taco, modifier_group=picante_group, display_order=1)
            )
            session.add(
                MenuItemModifierGroup(menu_item=taco, modifier_group=salsas_group, display_order=2)
            )

        # Asociar grupos OBLIGATORIOS a pizzas
        for pizza in pizzas_items:
            session.add(
                MenuItemModifierGroup(
                    menu_item=pizza, modifier_group=base_pizza_group, display_order=1
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=pizza, modifier_group=extra_pizza_group, display_order=2
                )
            )

        # Asociar grupos OBLIGATORIOS a ensaladas
        for ensalada in ensaladas_items:
            session.add(
                MenuItemModifierGroup(
                    menu_item=ensalada, modifier_group=aderezo_ensalada_group, display_order=1
                )
            )
            session.add(
                MenuItemModifierGroup(
                    menu_item=ensalada, modifier_group=vegetales_group, display_order=2
                )
            )

        # Asociar grupos OBLIGATORIOS a postres
        for postre in postres_items:
            session.add(
                MenuItemModifierGroup(
                    menu_item=postre, modifier_group=topping_postre_group, display_order=1
                )
            )

    existing_customer = session.execute(select(Customer).limit(1)).scalars().one_or_none()
    if existing_customer is None:
        guest_customer = Customer()
        guest_customer.name = "Invitado"
        guest_customer.email = "guest@example.com"
        guest_customer.phone = "+3499999999"
        session.add(guest_customer)

    permissions = session.execute(select(RoutePermission)).scalars().all()
    if not permissions:
        seed_permissions = [
            RoutePermission(
                code="waiter-board",
                display_name="Panel de meseros",
                description="Gestiona aceptaciones y entregas",
                app_target="employee",
            ),
            RoutePermission(
                code="kitchen-board",
                display_name="Panel de cocina",
                description="Gestión de preparación",
                app_target="employee",
            ),
            RoutePermission(
                code="admin-roles",
                display_name="Administrador de roles",
                description="Gestiona accesos ABC",
                app_target="employee",
            ),
            RoutePermission(
                code="content-manager",
                display_name="Gestor de contenido",
                description="Gestiona recursos estáticos",
                app_target="employee",
            ),
        ]
        session.add_all(seed_permissions)
        session.flush()

    existing_employees = session.execute(select(Employee)).scalars().all()
    if not existing_employees:
        import json as json_lib

        from shared.security import hash_credentials
        from shared.validation import validate_password

        default_password = os.getenv("SEED_EMPLOYEE_PASSWORD", "ChangeMe!123")
        validate_password(default_password)

        # Super Admin - has all scopes
        super_admin = Employee(role="super_admin")
        super_admin.name = "Admin General"
        super_admin.email = "admin@cafeteria.test"
        super_admin.auth_hash = hash_credentials(super_admin.email, default_password)
        super_admin.allow_scopes = json_lib.dumps(["admin", "waiter", "chef", "cashier"])
        session.add(super_admin)
        session.flush()

        # Admin de roles - has all scopes
        admin_roles = Employee(role="admin")
        admin_roles.name = "Admin Roles"
        admin_roles.email = "admin.roles@cafeteria.test"
        admin_roles.auth_hash = hash_credentials(admin_roles.email, default_password)
        admin_roles.allow_scopes = json_lib.dumps(["admin", "waiter", "chef", "cashier"])
        session.add(admin_roles)

        # Meseros - have waiter scope
        waiter1 = Employee(role="waiter")
        waiter1.name = "Juan Mesero"
        waiter1.email = "juan.mesero@cafeteria.test"
        waiter1.auth_hash = hash_credentials(waiter1.email, default_password)
        waiter1.allow_scopes = json_lib.dumps(["waiter"])
        session.add(waiter1)

        waiter2 = Employee(role="waiter")
        waiter2.name = "Maria Mesera"
        waiter2.email = "maria.mesera@cafeteria.test"
        waiter2.auth_hash = hash_credentials(waiter2.email, default_password)
        waiter2.allow_scopes = json_lib.dumps(["waiter"])
        session.add(waiter2)

        waiter3 = Employee(role="waiter")
        waiter3.name = "Pedro Mesero"
        waiter3.email = "pedro.mesero@cafeteria.test"
        waiter3.auth_hash = hash_credentials(waiter3.email, default_password)
        waiter3.allow_scopes = json_lib.dumps(["waiter"])
        session.add(waiter3)

        # Chefs - have chef scope
        chef1 = Employee(role="chef")
        chef1.name = "Carlos Chef"
        chef1.email = "carlos.chef@cafeteria.test"
        chef1.auth_hash = hash_credentials(chef1.email, default_password)
        chef1.allow_scopes = json_lib.dumps(["chef"])
        session.add(chef1)

        chef2 = Employee(role="chef")
        chef2.name = "Ana Chef"
        chef2.email = "ana.chef@cafeteria.test"
        chef2.auth_hash = hash_credentials(chef2.email, default_password)
        chef2.allow_scopes = json_lib.dumps(["chef"])
        session.add(chef2)

        # Cajeros - have cashier scope
        cashier1 = Employee(role="cashier")
        cashier1.name = "Laura Cajera"
        cashier1.email = "laura.cajera@cafeteria.test"
        cashier1.auth_hash = hash_credentials(cashier1.email, default_password)
        cashier1.allow_scopes = json_lib.dumps(["cashier"])
        session.add(cashier1)

        cashier2 = Employee(role="cashier")
        cashier2.name = "Roberto Cajero"
        cashier2.email = "roberto.cajero@cafeteria.test"
        cashier2.auth_hash = hash_credentials(cashier2.email, default_password)
        cashier2.allow_scopes = json_lib.dumps(["cashier"])
        session.add(cashier2)

        # Content Manager - has admin scope
        content = Employee(role="content_manager")
        content.name = "Sofia Contenido"
        content.email = "sofia.contenido@cafeteria.test"
        content.auth_hash = hash_credentials(content.email, default_password)
        content.allow_scopes = json_lib.dumps(["admin"])
        session.add(content)

        session.flush()

        permissions_map = {
            perm.code: perm for perm in session.execute(select(RoutePermission)).scalars().all()
        }

        # Super admin tiene todos los permisos
        for perm in permissions_map.values():
            session.add(
                EmployeeRouteAccess(employee_id=super_admin.id, route_permission_id=perm.id)
            )

        # Admin roles tiene permisos de gestión de roles
        if "admin-roles" in permissions_map:
            session.add(
                EmployeeRouteAccess(employee=admin_roles, permission=permissions_map["admin-roles"])
            )

        # Meseros tienen acceso al panel de meseros
        if "waiter-board" in permissions_map:
            for waiter in [waiter1, waiter2, waiter3]:
                session.add(
                    EmployeeRouteAccess(employee=waiter, permission=permissions_map["waiter-board"])
                )

        # Chefs tienen acceso al panel de cocina
        if "kitchen-board" in permissions_map:
            for chef in [chef1, chef2]:
                session.add(
                    EmployeeRouteAccess(employee=chef, permission=permissions_map["kitchen-board"])
                )

        # Content manager
        if "content-manager" in permissions_map:
            session.add(
                EmployeeRouteAccess(employee=content, permission=permissions_map["content-manager"])
            )
    else:
        _assign_missing_employee_identity(session)

    # Business Configuration Parameters
    existing_config = session.execute(select(BusinessConfig)).scalars().all()
    if not existing_config:
        default_configs = [
            BusinessConfig(
                config_key="waiter_call_timeout_seconds",
                config_value="60",
                value_type="int",
                category="notifications",
                display_name="Timeout de llamada al mesero",
                description="Tiempo en segundos que la campanita permanece en rojo después de llamar al mesero",
                min_value=Decimal("10"),
                max_value=Decimal("300"),
                unit="seconds",
            ),
            BusinessConfig(
                config_key="order_auto_accept_minutes",
                config_value="5",
                value_type="int",
                category="orders",
                display_name="Auto-aceptación de órdenes",
                description="Minutos antes de auto-aceptar una orden si no hay mesero disponible",
                min_value=Decimal("1"),
                max_value=Decimal("30"),
                unit="minutes",
            ),
            BusinessConfig(
                config_key="tip_default_percentage",
                config_value="10",
                value_type="int",
                category="payments",
                display_name="Propina por defecto",
                description="Porcentaje de propina sugerido por defecto",
                min_value=Decimal("0"),
                max_value=Decimal("25"),
                unit="percent",
            ),
            BusinessConfig(
                config_key="checkout_default_method",
                config_value="cash",
                value_type="string",
                category="payments",
                display_name="Método por defecto al pedir cuenta",
                description="Opciones: cash, terminal, digital. Define cómo se manejará el cobro si el cliente no responde al modal.",
            ),
            BusinessConfig(
                config_key="checkout_prompt_duration_seconds",
                config_value="6",
                value_type="int",
                category="payments",
                display_name="Duración del formulario de cobro",
                description="Segundos que se muestra la tarjeta flotante con las opciones de pago al cliente.",
                min_value=Decimal("3"),
                max_value=Decimal("30"),
                unit="seconds",
            ),
            BusinessConfig(
                config_key="session_auto_close_hours",
                config_value="24",
                value_type="int",
                category="sessions",
                display_name="Cierre automático de sesiones",
                description="Horas después de las cuales una sesión inactiva se cierra automáticamente",
                min_value=Decimal("1"),
                max_value=Decimal("72"),
                unit="hours",
            ),
            BusinessConfig(
                config_key="kitchen_preparation_alert_minutes",
                config_value="15",
                value_type="int",
                category="kitchen",
                display_name="Alerta de tiempo de preparación",
                description="Minutos después de los cuales se alerta si una orden no está lista",
                min_value=Decimal("5"),
                max_value=Decimal("60"),
                unit="minutes",
            ),
            BusinessConfig(
                config_key="currency_code",
                config_value="MXN",
                value_type="string",
                category="payments",
                display_name="Moneda principal",
                description="Código ISO 4217 usado para mostrar precios al cliente",
                unit="currency",
            ),
            BusinessConfig(
                config_key="currency_locale",
                config_value="es-MX",
                value_type="string",
                category="payments",
                display_name="Formato numérico",
                description="Locale usado para renderizar cantidades",
                unit="locale",
            ),
            BusinessConfig(
                config_key="currency_symbol",
                config_value="$",
                value_type="string",
                category="payments",
                display_name="Símbolo de moneda",
                description="Símbolo mostrado junto a los importes",
            ),
            BusinessConfig(
                config_key="default_country_code",
                config_value="+52",
                value_type="string",
                category="customers",
                display_name="Lada por defecto",
                description="Prefijo telefónico que se sugiere en el formulario de clientes",
            ),
            BusinessConfig(
                config_key="phone_country_options",
                config_value=json.dumps(
                    [
                        {"iso": "MX", "label": "México", "dial_code": "+52", "flag": "🇲🇽"},
                        {"iso": "US", "label": "Estados Unidos", "dial_code": "+1", "flag": "🇺🇸"},
                        {"iso": "ES", "label": "España", "dial_code": "+34", "flag": "🇪🇸"},
                    ]
                ),
                value_type="json",
                category="customers",
                display_name="Ladas disponibles",
                description="Lista de prefijos telefónicos disponibles en el formulario",
                unit="json",
            ),
            BusinessConfig(
                config_key="items_per_page",
                config_value="10",
                value_type="select",
                category="general",
                display_name="Elementos por página",
                description="Número de elementos a mostrar por página en listas y catálogos. Opciones: 10, 25, 50, 100",
                min_value=Decimal("10"),
                max_value=Decimal("100"),
                unit="items",
            ),
            BusinessConfig(
                config_key="client_session_cookie_name",
                config_value="pronto_client",
                value_type="string",
                category="security",
                display_name="Nombre de cookie de clientes",
                description="Nombre de la cookie de sesión para la aplicación de clientes. Cambiar este valor requiere reiniciar la aplicación.",
            ),
            BusinessConfig(
                config_key="employee_session_cookie_name",
                config_value="pronto_employee",
                value_type="string",
                category="security",
                display_name="Nombre de cookie de empleados",
                description="Nombre de la cookie de sesión para la aplicación de empleados. Cambiar este valor requiere reiniciar la aplicación.",
            ),
            BusinessConfig(
                config_key="store_cancel_reason",
                config_value="true",
                value_type="bool",
                category="orders",
                display_name="Guardar motivo de cancelación",
                description="Si está activo se guardan los motivos cuando cliente o mesero cancelan una orden.",
            ),
            BusinessConfig(
                config_key="paid_orders_window_minutes",
                config_value="15",
                value_type="int",
                category="orders",
                display_name="Ventana de órdenes pagadas (min)",
                description="Minutos que las órdenes pagadas permanecen visibles antes de ocultarse.",
                min_value=Decimal("1"),
                max_value=Decimal("120"),
                unit="minutes",
            ),
            BusinessConfig(
                config_key="realtime_poll_interval_ms",
                config_value="1000",
                value_type="int",
                category="advanced",
                display_name="Intervalo de polling realtime (ms)",
                description="Intervalo en milisegundos para consultar eventos en tiempo real.",
                min_value=Decimal("250"),
                max_value=Decimal("10000"),
                unit="ms",
            ),
            BusinessConfig(
                config_key="client_session_validation_interval_minutes",
                config_value="10",
                value_type="int",
                category="sessions",
                display_name="Intervalo de validación de sesión (cliente)",
                description="Minutos para validar que la sesión del cliente siga activa en el backend.",
                min_value=Decimal("1"),
                max_value=Decimal("120"),
                unit="minutes",
            ),
            BusinessConfig(
                config_key="waiter_call_cooldown_seconds",
                config_value="10",
                value_type="int",
                category="notifications",
                display_name="Cooldown de campanita (segundos)",
                description="Tiempo en segundos que la campanita permanece roja después de confirmar.",
                min_value=Decimal("10"),
                max_value=Decimal("300"),
                unit="seconds",
            ),
            BusinessConfig(
                config_key="waiter_call_sound",
                config_value="bell1.mp3",
                value_type="string",
                category="notifications",
                display_name="Sonido de campanita",
                description="Audio usado para las notificaciones de llamada al mesero.",
            ),
            BusinessConfig(
                config_key="closed_sessions_history_hours",
                config_value="24",
                value_type="int",
                category="orders",
                display_name="Histórico de órdenes cerradas (horas)",
                description="Horas hacia atrás para mostrar órdenes cerradas.",
                min_value=Decimal("1"),
                max_value=Decimal("168"),
                unit="hours",
            ),
            BusinessConfig(
                config_key="price_display_mode",
                config_value="tax_included",
                value_type="string",
                category="advanced",
                display_name="Método de presentación de precios",
                description="Define cómo se muestran los precios al cliente. tax_included o tax_excluded.",
                unit="mode",
            ),
            BusinessConfig(
                config_key="paid_orders_retention_minutes",
                config_value="60",
                value_type="int",
                category="orders",
                display_name="Retención de órdenes pagadas (min)",
                description="Minutos que las órdenes pagadas se mantienen visibles en el panel.",
                min_value=Decimal("5"),
                max_value=Decimal("240"),
                unit="minutes",
            ),
            BusinessConfig(
                config_key="payment_action_delay_seconds",
                config_value="5",
                value_type="int",
                category="payments",
                display_name="Delay de acciones de pago (segundos)",
                description="Espera en segundos antes de ejecutar acciones posteriores al pago.",
                min_value=Decimal("0"),
                max_value=Decimal("30"),
                unit="seconds",
            ),
        ]
        session.add_all(default_configs)
        existing_config = default_configs

    existing_keys = {config.config_key for config in existing_config}
    if "checkout_default_method" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="checkout_default_method",
                config_value="cash",
                value_type="string",
                category="payments",
                display_name="Método por defecto al pedir cuenta",
                description="Opciones: cash, terminal o digital. Define cómo se atiende la cuenta cuando el cliente no responde.",
            )
        )
    if "checkout_prompt_duration_seconds" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="checkout_prompt_duration_seconds",
                config_value="6",
                value_type="int",
                category="payments",
                display_name="Duración del formulario de cobro",
                description="Segundos que permanece visible el formulario flotante para elegir método de pago.",
            )
        )
    if "items_per_page" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="items_per_page",
                config_value="10",
                value_type="select",
                category="general",
                display_name="Elementos por página",
                description="Número de elementos a mostrar por página en listas y catálogos. Opciones: 10, 25, 50, 100",
                min_value=Decimal("10"),
                max_value=Decimal("100"),
                unit="items",
            )
        )
    if "store_cancel_reason" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="store_cancel_reason",
                config_value="true",
                value_type="bool",
                category="orders",
                display_name="Guardar motivo de cancelación",
                description="Si está activo se guardan los motivos cuando cliente o mesero cancelan una orden.",
            )
        )
    if "paid_orders_window_minutes" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="paid_orders_window_minutes",
                config_value="15",
                value_type="int",
                category="orders",
                display_name="Ventana de órdenes pagadas (min)",
                description="Minutos que las órdenes pagadas permanecen visibles antes de ocultarse.",
                min_value=Decimal("1"),
                max_value=Decimal("120"),
                unit="minutes",
            )
        )
    if "realtime_poll_interval_ms" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="realtime_poll_interval_ms",
                config_value="1000",
                value_type="int",
                category="advanced",
                display_name="Intervalo de polling realtime (ms)",
                description="Intervalo en milisegundos para consultar eventos en tiempo real.",
                min_value=Decimal("250"),
                max_value=Decimal("10000"),
                unit="ms",
            )
        )
    if "client_session_validation_interval_minutes" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="client_session_validation_interval_minutes",
                config_value="10",
                value_type="int",
                category="sessions",
                display_name="Intervalo de validación de sesión (cliente)",
                description="Minutos para validar que la sesión del cliente siga activa en el backend.",
                min_value=Decimal("1"),
                max_value=Decimal("120"),
                unit="minutes",
            )
        )
    if "waiter_call_cooldown_seconds" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="waiter_call_cooldown_seconds",
                config_value="10",
                value_type="int",
                category="notifications",
                display_name="Cooldown de campanita (segundos)",
                description="Tiempo en segundos que la campanita permanece roja después de confirmar.",
                min_value=Decimal("10"),
                max_value=Decimal("300"),
                unit="seconds",
            )
        )
    if "waiter_call_sound" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="waiter_call_sound",
                config_value="bell1.mp3",
                value_type="string",
                category="notifications",
                display_name="Sonido de campanita",
                description="Audio usado para las notificaciones de llamada al mesero.",
            )
        )
    if "closed_sessions_history_hours" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="closed_sessions_history_hours",
                config_value="24",
                value_type="int",
                category="orders",
                display_name="Histórico de órdenes cerradas (horas)",
                description="Horas hacia atrás para mostrar órdenes cerradas.",
                min_value=Decimal("1"),
                max_value=Decimal("168"),
                unit="hours",
            )
        )
    if "price_display_mode" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="price_display_mode",
                config_value="tax_included",
                value_type="string",
                category="advanced",
                display_name="Método de presentación de precios",
                description="Define cómo se muestran los precios al cliente. tax_included o tax_excluded.",
                unit="mode",
            )
        )
    if "paid_orders_retention_minutes" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="paid_orders_retention_minutes",
                config_value="60",
                value_type="int",
                category="orders",
                display_name="Retención de órdenes pagadas (min)",
                description="Minutos que las órdenes pagadas se mantienen visibles en el panel.",
                min_value=Decimal("5"),
                max_value=Decimal("240"),
                unit="minutes",
            )
        )
    if "payment_action_delay_seconds" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="payment_action_delay_seconds",
                config_value="5",
                value_type="int",
                category="payments",
                display_name="Delay de acciones de pago (segundos)",
                description="Espera en segundos antes de ejecutar acciones posteriores al pago.",
                min_value=Decimal("0"),
                max_value=Decimal("30"),
                unit="seconds",
            )
        )
    if "unassigned_table_alert_minutes" not in existing_keys:
        session.add(
            BusinessConfig(
                config_key="unassigned_table_alert_minutes",
                config_value="5",
                value_type="int",
                category="advanced",
                display_name="Minutos para alertar mesas sin asignar",
                description="Minutos que una mesa puede estar sin mesero antes de enviar alerta al administrador.",
            )
        )

    # Tables with QR codes - normalize existing and seed missing
    existing_tables = session.execute(select(Table)).scalars().all()

    def normalize_table_record(table: Table) -> bool:
        try:
            table.table_number = validate_table_code(table.table_number)
            return True
        except ValidationError:
            pass
        digits_match = re.search(r"(\d+)", table.table_number or "")
        table_num = int(digits_match.group(1)) if digits_match else 0
        if table_num < 1 or table_num > 99:
            return False
        if not table.area_id:
            return False
        area = session.get(Area, table.area_id)
        if not area:
            return False
        area_code = area.prefix or "G"
        try:
            code = build_table_code(area_code, table_num)
        except ValidationError:
            return False
        table.table_number = code
        table.qr_code = _generate_qr_code(code, restaurant_slug)
        return True

    updated_any = False
    for table in existing_tables:
        if normalize_table_record(table):
            updated_any = True
    if updated_any:
        session.flush()

    if not existing_tables:
        areas = {a.name: a for a in session.execute(select(Area)).scalars().all()}
        tables_to_create = []

        interior_area = areas.get("Interior")
        if interior_area:
            for i in range(1, 11):
                code = build_table_code(interior_area.prefix or "I", i)
                tables_to_create.append(
                    Table(
                        table_number=code,
                        qr_code=_generate_qr_code(code, restaurant_slug),
                        area_id=interior_area.id,
                        capacity=4 if i <= 8 else 6,
                        position_x=((i - 1) % 4) * 100,
                        position_y=((i - 1) // 4) * 100,
                        shape="square",
                    )
                )

        terraza_area = areas.get("Terraza")
        if terraza_area:
            for i in range(11, 19):
                code = build_table_code(terraza_area.prefix or "T", i)
                tables_to_create.append(
                    Table(
                        table_number=code,
                        qr_code=_generate_qr_code(code, restaurant_slug),
                        area_id=terraza_area.id,
                        capacity=4,
                        position_x=((i - 11) % 4) * 100,
                        position_y=((i - 11) // 4) * 100,
                        shape="round",
                    )
                )

        bar_area = areas.get("Bar")
        if bar_area:
            for i in range(1, 5):
                code = build_table_code(bar_area.prefix or "B", i)
                tables_to_create.append(
                    Table(
                        table_number=code,
                        qr_code=_generate_qr_code(code, restaurant_slug),
                        area_id=bar_area.id,
                        capacity=2,
                        position_x=(i - 1) * 80,
                        position_y=0,
                        shape="rectangular",
                    )
                )

        vip_area = areas.get("VIP")
        if vip_area:
            for i in range(1, 4):
                code = build_table_code(vip_area.prefix or "V", i)
                tables_to_create.append(
                    Table(
                        table_number=code,
                        qr_code=_generate_qr_code(code, restaurant_slug),
                        area_id=vip_area.id,
                        capacity=6 if i == 1 else 8,
                        position_x=(i - 1) * 150,
                        position_y=0,
                        shape="round",
                    )
                )

        session.add_all(tables_to_create)

    # ==================== GENERAL TABLES (M-MXX) ====================
    # Ensure generic tables exist for "Mesa 1" inputs (mapped to M-M01)
    # Check by table_number pattern instead of zone
    general_tables = (
        session.execute(select(Table).where(Table.table_number.like("M-M%"))).scalars().all()
    )

    logger.info(f"[SEED] Checking General tables. Found {len(general_tables)} existing.")

    if not general_tables:
        logger.info("[SEED] Creating General tables...")
        general_tables = []
        for i in range(1, 6):
            code = build_table_code("M", i)
            logger.info(f"[SEED] Processing table {code}")

            existing_t = session.execute(
                select(Table).where(Table.table_number == code)
            ).scalar_one_or_none()
            if existing_t:
                logger.info(f"[SEED] Table {code} already exists, skipping.")
                continue

            general_tables.append(
                Table(
                    table_number=code,
                    qr_code=_generate_qr_code(code, restaurant_slug),
                    capacity=4,
                    position_x=(i - 1) * 100,
                    position_y=400,
                    shape="square",
                )
            )
        if general_tables:
            logger.info(f"[SEED] Adding {len(general_tables)} generic tables.")
            session.add_all(general_tables)
            session.flush()

    existing_feedback = session.execute(select(Feedback).limit(1)).scalars().one_or_none()
    if not existing_feedback:
        customer = session.execute(select(Customer).order_by(Customer.id)).scalars().first()
        employee = session.execute(select(Employee).order_by(Employee.id)).scalars().first()
        if customer:
            sessions = (
                session.execute(select(DiningSession).order_by(DiningSession.id).limit(3))
                .scalars()
                .all()
            )

            if not sessions:
                table = session.execute(select(Table).order_by(Table.id)).scalars().first()
                base_time = datetime.utcnow() - timedelta(days=7)
                for i in range(3):
                    opened_at = base_time + timedelta(days=i, hours=11)
                    closed_at = opened_at + timedelta(hours=2, minutes=15)
                    sessions.append(
                        DiningSession(
                            customer_id=customer.id,
                            table_id=table.id if table else None,
                            table_number=table.table_number if table else None,
                            status="closed",
                            opened_at=opened_at,
                            closed_at=closed_at,
                        )
                    )
                session.add_all(sessions)

            session.flush()

            seed_categories = [
                FeedbackCategory.WAITER_SERVICE.value,
                FeedbackCategory.FOOD_QUALITY.value,
                FeedbackCategory.OVERALL_EXPERIENCE.value,
            ]
            ratings_cycle = [5, 4, 5]
            comments_cycle = [
                "Excelente atencion y rapidez.",
                "La comida estuvo muy buena.",
                "Muy buena experiencia en general.",
            ]

            for idx, sess in enumerate(sessions[:3]):
                created_at = datetime.utcnow() - timedelta(days=idx + 1)
                for cat_index, category in enumerate(seed_categories):
                    feedback = Feedback(
                        session_id=sess.id,
                        customer_id=customer.id,
                        employee_id=employee.id if employee else None,
                        category=category,
                        rating=ratings_cycle[cat_index % len(ratings_cycle)],
                        comment=comments_cycle[cat_index % len(comments_cycle)],
                        is_anonymous=False,
                        created_at=created_at,
                    )
                    session.add(feedback)

    session.flush()

    # ==================== BUSINESS SCHEDULE ====================
    existing_schedules = session.execute(select(BusinessSchedule)).scalars().all()
    if not existing_schedules:
        schedules = []
        for day in range(7):  # 0=Monday to 6=Sunday
            schedules.append(
                BusinessSchedule(
                    day_of_week=day,
                    is_open=True,
                    open_time="00:00",
                    close_time="23:59",
                    notes="Abierto todo el día (Seed Data)",
                )
            )
        session.add_all(schedules)
        session.flush()


def _seed_system_permissions(session) -> None:
    """Seed granular permissions and roles."""
    from shared.permissions import ROLE_PERMISSIONS, Permission

    # Sync SystemPermissions
    all_perms_enum = list(Permission)
    perm_code_to_id = {}

    for p_enum in all_perms_enum:
        stmt = select(SystemPermission).where(SystemPermission.code == p_enum.value)
        existing = session.execute(stmt).scalars().first()

        category = p_enum.value.split(":")[0]
        description = f"Permission to {p_enum.value.replace(':', ' ')}"

        if existing:
            existing.category = category
            perm_code_to_id[p_enum.value] = existing.id
        else:
            new_perm = SystemPermission(
                code=p_enum.value, category=category, description=description
            )
            session.add(new_perm)
            session.flush()
            perm_code_to_id[p_enum.value] = new_perm.id

    # Sync Roles and Bindings
    for role_name, permissions_set in ROLE_PERMISSIONS.items():
        # Check/Create Role
        stmt = select(SystemRole).where(SystemRole.name == role_name)
        role = session.execute(stmt).scalars().first()

        if not role:
            role = SystemRole(
                name=role_name,
                display_name=role_name.replace("_", " ").title(),
                description=f"System role for {role_name}",
                is_custom=False,
            )
            session.add(role)
            session.flush()

        # Update bindings safely (check if exists to avoid race conditions/unique violations)
        for p_enum in permissions_set:
            perm_id = perm_code_to_id.get(p_enum.value)
            if perm_id:
                # Check if binding exists
                binding_stmt = select(RolePermissionBinding).where(
                    RolePermissionBinding.role_id == role.id,
                    RolePermissionBinding.permission_id == perm_id,
                )
                if not session.execute(binding_stmt).scalars().first():
                    session.add(RolePermissionBinding(role_id=role.id, permission_id=perm_id))

    # Flush changes but let the caller commit
    session.flush()


from sqlalchemy.exc import IntegrityError


def ensure_seed_data(session) -> None:
    """Legacy seed runner that only executes when the DB is empty."""
    try:
        restaurant_slug = _slugify(os.getenv("RESTAURANT_NAME", "pronto"))
        _ensure_seed_data_impl(session, restaurant_slug)
        _seed_system_permissions(session)
        session.commit()
    except IntegrityError:
        # Handle race conditions in multi-worker environment
        # If another worker inserted the data concurrently, we can safely ignore
        session.rollback()
    except Exception:
        session.rollback()
        raise
