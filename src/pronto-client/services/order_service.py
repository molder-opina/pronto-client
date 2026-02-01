"""
Service helper to validate and store client orders.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from clients_app.utils.input_sanitizer import (
    InputValidationError,
    sanitize_customer_name,
    sanitize_email,
    sanitize_notes,
    sanitize_phone,
)
from pronto_shared.config import SESSION_TTL_HOURS
from pronto_shared.constants import OrderStatus
from pronto_shared.db import get_session
from pronto_shared.models import (
    Customer,
    DiningSession,
    MenuItem,
    MenuItemModifierGroup,
    Modifier,
    ModifierGroup,
    Order,
    OrderItem,
    OrderItemModifier,
)
from pronto_shared.security import hash_identifier
from pronto_shared.services.price_service import calculate_price_breakdown, get_price_display_mode

logger = logging.getLogger(__name__)


def _debug(msg: str, **kwargs):
    """Debug helper that logs to logger.info/debug"""
    if kwargs:
        msg = f"{msg} | {kwargs}"
    logger.info(f"[DEBUG_ORDER] {msg}")


class OrderValidationError(Exception):
    """Raised when the incoming order payload is invalid."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def validate_payload(
    customer_data: dict[str, Any], items_data: list[dict[str, Any]], require_contact: bool = True
) -> None:
    """
    Validate order payload.

    If require_contact is True (default), requires email OR phone for sending ticket.
    """
    if require_contact:
        has_email = bool((customer_data.get("email") or "").strip())
        has_phone = bool((customer_data.get("phone") or "").strip())
        if not has_email and not has_phone:
            raise OrderValidationError("Proporciona tu email o teléfono para recibir el ticket")

    if not items_data:
        raise OrderValidationError("Debes seleccionar al menos un producto")


def validate_required_modifiers(
    session, menu_item_id: int, selected_modifiers: list[dict[str, Any]]
) -> None:
    """
    Validate that all required modifier groups have been selected with the correct quantities.

    Args:
        session: Database session
        menu_item_id: The menu item ID
        selected_modifiers: List of selected modifiers.
            - New format: [{"modifier_id": int, "quantity": int}]
            - Legacy/TS format: [modifier_id, modifier_id, ...]

    Raises:
        OrderValidationError: If required modifiers are missing or invalid
    """
    # Get all modifier groups for this menu item
    menu_item_groups = session.execute(
        select(MenuItemModifierGroup, ModifierGroup)
        .join(ModifierGroup, MenuItemModifierGroup.modifier_group_id == ModifierGroup.id)
        .where(MenuItemModifierGroup.menu_item_id == menu_item_id)
    ).all()

    # Count selected modifiers by group
    selected_by_group: dict[int, int] = {}
    for selected in selected_modifiers:
        # Support both dict payloads and simple integer IDs
        if isinstance(selected, dict):
            modifier_id = selected.get("modifier_id")
            quantity = int(selected.get("quantity", 1) or 1)
        else:
            # Legacy/TS payload where "modifiers" is a list of IDs
            modifier_id = int(selected)
            quantity = 1

        if not modifier_id:
            continue

        # Get the modifier's group
        modifier = session.get(Modifier, modifier_id)
        if modifier:
            group_id = modifier.group_id
            if group_id not in selected_by_group:
                selected_by_group[group_id] = 0
            selected_by_group[group_id] += quantity

    # Validate each required group
    for _item_group, group in menu_item_groups:
        if group.is_required:
            selected_count = selected_by_group.get(group.id, 0)

            if selected_count < group.min_selection:
                # Get the menu item name for better error message
                menu_item = session.get(MenuItem, menu_item_id)
                item_name = menu_item.name if menu_item else "este producto"

                if group.min_selection == group.max_selection and group.min_selection > 0:
                    is_dressing = "aderezo" in (group.name or "").lower()
                    label = "aderezos incluidos" if is_dressing else "opción(es)"
                    raise OrderValidationError(
                        f"Por favor, selecciona {group.min_selection} {label} de '{group.name}' para '{item_name}'. "
                        f"Edita el producto en tu carrito para completar esta selección."
                    )
                raise OrderValidationError(
                    f"Por favor, selecciona al menos {group.min_selection} opción(es) de '{group.name}' para '{item_name}'. "
                    f"Edita el producto en tu carrito para completar esta selección."
                )

            if selected_count > group.max_selection:
                raise OrderValidationError(
                    f"No puedes seleccionar más de {group.max_selection} opción(es) de '{group.name}'"
                )


def create_order(
    customer_data: dict[str, Any],
    items_data: list[dict[str, Any]],
    notes: str | None,
    tax_rate: float,
    existing_session_id: int | None = None,
    table_number: str | None = None,
    anonymous_client_id: str | None = None,
    auto_ready_quick_serve: bool = False,
) -> tuple[dict, HTTPStatus]:
    """
    Persist an order and return a tuple with the response dictionary and status code.
    """
    validate_payload(customer_data, items_data)

    tax_decimal = Decimal(str(tax_rate)).quantize(Decimal("0.0001"))

    try:
        sanitized_name = sanitize_customer_name(
            customer_data.get("name"), allow_empty=True, default="INVITADO"
        )
        sanitized_phone = sanitize_phone(customer_data.get("phone"))
        sanitized_notes = sanitize_notes(notes)
    except InputValidationError as exc:
        raise OrderValidationError(str(exc), status=HTTPStatus.BAD_REQUEST)

    with get_session() as session:
        try:
            email_value = sanitize_email(customer_data.get("email"), allow_empty=True)
        except InputValidationError as exc:
            raise OrderValidationError(str(exc), status=HTTPStatus.BAD_REQUEST)
        phone_value = sanitized_phone

        _debug("Starting customer creation/lookup", email=email_value, phone=phone_value)

        # Para compra anónima, usar email temporal si no se proporciona
        if not email_value:
            # Usar anonymous_client_id si está disponible, sino generar uno
            if anonymous_client_id:
                email_value = f"anonimo+{anonymous_client_id}@temp.local"
            elif phone_value:
                email_value = f"anonimo+{phone_value.replace('+', '')}@temp.local"
            else:
                import uuid

                email_value = f"anonimo+{uuid.uuid4().hex[:8]}@temp.local"

        # Ensure generated address is normalized as well
        email_value = sanitize_email(email_value)

        email_hash = hash_identifier(email_value)

        customer = session.query(Customer).filter(Customer.email_hash == email_hash).one_or_none()
        if customer is None:
            customer = Customer()
            customer.name = sanitized_name or "INVITADO"
            customer.email = email_value
            customer.phone = phone_value or None
            session.add(customer)
            session.flush()
        else:
            if customer_data.get("name"):
                customer.name = sanitized_name
            # Actualizar email solo si no es temporal
            if not email_value.startswith("anonimo+"):
                customer.email = email_value

        if phone_value:
            customer.phone = phone_value

        # Resolve table_id from table_number BEFORE session lookup
        def get_valid_table(recorded_table_number: str | None, allow_fallback: bool = False):
            from pronto_shared.models import Table

            normalized = (recorded_table_number or "").strip()
            table = None

            if normalized:
                table = (
                    session.execute(
                        select(Table).where(
                            Table.is_active,
                            func.lower(Table.table_number) == func.lower(normalized),
                        )
                    )
                    .scalars()
                    .first()
                )

            if table:
                return table

            if allow_fallback:
                # Fallback only when explicitly allowed (e.g., creating a new session without a valid table)
                return (
                    session.execute(select(Table).where(Table.is_active).order_by(Table.id))
                    .scalars()
                    .first()
                )

            return None

        # First, resolve the table to get table_id for session lookup
        table_record = get_valid_table(table_number, allow_fallback=False)
        table_id = table_record.id if table_record else None
        resolved_table_number = table_record.table_number if table_record else table_number

        # LOCKING: Lock the table row to prevent race conditions when checking/creating sessions
        if table_id:
            try:
                # Use plain execute with SQL to avoid issues with model imports or detaching
                from pronto_shared.models import Table

                session.execute(select(Table).where(Table.id == table_id).with_for_update())
                _debug(f"Acquired lock for table_id {table_id}")
            except Exception as lock_err:
                logger.warning(f"Could not acquire table lock: {lock_err}")

        _debug(f"Resolved table: {resolved_table_number} (ID: {table_id})")

        # Session lookup strategy:
        # 1. Try to use existing_session_id from client if valid
        # 2. Search for open session by table (prevents duplicates for same table)
        # 3. Search for open session by customer_id (fallback for customers without table)
        # 4. Create new session if none found

        dining_session: DiningSession | None = None

        # Step 1: Check if client provided a valid session_id
        if existing_session_id:
            dining_session = session.get(DiningSession, existing_session_id)
            # Validate the session: must exist, be open, and not expired
            if dining_session and dining_session.status == "open":
                # Check TTL expiration
                if getattr(dining_session, "is_expired", False):
                    logger.info(f"Session {existing_session_id} has expired, closing it")
                    dining_session.status = "closed"
                    session.flush()
                    dining_session = None
                else:
                    # Session is valid - we'll use it
                    logger.info(
                        f"Reusing existing session {existing_session_id} for customer {customer.id}"
                    )
            else:
                # Session doesn't exist or is closed
                logger.info(
                    f"Session {existing_session_id} is invalid (not found or closed), will search for another"
                )
                dining_session = None

        # Step 2: If no valid session from client, search by TABLE first (key fix for duplicates)
        if dining_session is None and table_id:
            dining_session = (
                session.execute(
                    select(DiningSession)
                    .where(
                        DiningSession.table_id == table_id,
                        DiningSession.status == "open",
                    )
                    .limit(1)
                )
                .scalars()
                .one_or_none()
            )
            # Check if found session is expired
            if dining_session and getattr(dining_session, "is_expired", False):
                logger.info(
                    f"Found session {dining_session.id} for table {table_id} but it has expired"
                )
                dining_session.status = "closed"
                session.flush()
                dining_session = None
            if dining_session:
                logger.info(
                    f"Found existing open session {dining_session.id} for table {resolved_table_number} (table_id={table_id})"
                )

        # Step 3: If still no session, try searching by customer_id as fallback
        if dining_session is None:
            dining_session = (
                session.execute(
                    select(DiningSession)
                    .where(
                        DiningSession.customer_id == customer.id,
                        DiningSession.status == "open",
                    )
                    .limit(1)
                )
                .scalars()
                .one_or_none()
            )
            # Check if found session is expired (BUG FIX: was missing)
            if dining_session and getattr(dining_session, "is_expired", False):
                logger.info(
                    f"Found session {dining_session.id} for customer {customer.id} but it has expired"
                )
                dining_session.status = "closed"
                session.flush()
                dining_session = None
            elif dining_session:
                logger.info(
                    f"Found existing open session {dining_session.id} for customer {customer.id}"
                )

        # Step 4: Create new session if none found (get-or-create robust pattern)
        if dining_session is None:
            # Allow fallback to first available table only when creating brand new session
            if not table_id and not resolved_table_number:
                fallback_table = get_valid_table(None, allow_fallback=True)
                if fallback_table:
                    table_id = fallback_table.id
                    resolved_table_number = fallback_table.table_number

            # PATRÓN GET-OR-CREATE ROBUSTO:
            # 1) Buscar sesión open por table_id (incluso si ya se buscó, por si acaso)
            # 2) Si no existe, intentar crear con expires_at
            # 3) Si falla con IntegrityError (race condition), hacer rollback y re-consultar

            if table_id:
                # Try to find existing open session for this table (robust check)
                existing_by_table = (
                    session.execute(
                        select(DiningSession)
                        .where(
                            DiningSession.table_id == table_id,
                            DiningSession.status == "open",
                        )
                        .limit(1)
                    )
                    .scalars()
                    .one_or_none()
                )

                if existing_by_table and not getattr(existing_by_table, "is_expired", False):
                    # Reuse existing session (another request might have created it)
                    dining_session = existing_by_table
                    logger.info(
                        f"Reusing existing session {dining_session.id} for table {resolved_table_number} (concurrent request)"
                    )
                else:
                    # Try to create new session with expires_at (TTL)
                    try:
                        expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)

                        dining_session = DiningSession(
                            customer=customer,
                            status="open",
                            table_id=table_id,
                            table_number=resolved_table_number,
                            notes=sanitized_notes,
                            expires_at=expires_at,
                        )
                        session.add(dining_session)
                        session.flush()
                        logger.info(
                            f"Created new session {dining_session.id} for customer {customer.id} at table {resolved_table_number} with TTL {SESSION_TTL_HOURS}h"
                        )
                    except IntegrityError:
                        # Race condition: another request created the same session
                        # Rollback and re-query to find the existing session
                        session.rollback()
                        logger.warning(
                            f"Race condition detected for table {table_id}, re-querying existing session"
                        )

                        existing_by_table = (
                            session.execute(
                                select(DiningSession)
                                .where(
                                    DiningSession.table_id == table_id,
                                    DiningSession.status == "open",
                                )
                                .limit(1)
                            )
                            .scalars()
                            .one_or_none()
                        )

                        if existing_by_table:
                            dining_session = existing_by_table
                            logger.info(
                                f"Recovered session {dining_session.id} for table {resolved_table_number} after IntegrityError"
                            )
                        else:
                            # Should not happen, but handle gracefully
                            raise OrderValidationError(
                                f"Unable to create or recover session for table {resolved_table_number}",
                                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                            )
            else:
                # No table_id: create session without table constraint
                expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)

                dining_session = DiningSession(
                    customer=customer,
                    status="open",
                    table_id=table_id,
                    table_number=resolved_table_number,
                    notes=sanitized_notes,
                    expires_at=expires_at,
                )
                session.add(dining_session)
                session.flush()
                logger.info(
                    f"Created new session {dining_session.id} for customer {customer.id} (no table) with TTL {SESSION_TTL_HOURS}h"
                )
        else:
            # Fix sessions without valid table: align only when input is valid
            if table_id and dining_session.table_id != table_id:
                dining_session.table_id = table_id
                dining_session.table_number = resolved_table_number
            elif resolved_table_number and not dining_session.table_number:
                dining_session.table_number = resolved_table_number
            elif dining_session.table_number and not dining_session.table_id:
                # Try to resolve based on stored table_number, without falling back blindly
                fallback_table = get_valid_table(dining_session.table_number, allow_fallback=False)
                if fallback_table:
                    dining_session.table_id = fallback_table.id
                    dining_session.table_number = fallback_table.table_number
            if sanitized_notes:
                dining_session.notes = sanitized_notes

        # Cache table_id BEFORE creating order to avoid lazy-load issues later
        cached_table_id = dining_session.table_id

        _debug(
            f"Creating Order object for session {dining_session.id}, items count: {len(items_data)}"
        )

        order = Order(customer=customer, session=dining_session, customer_email=email_value)
        session.add(order)
        session.flush()

        _debug(f"Order created with ID: {order.id}")

        # Get price display mode for proper calculation
        price_mode = get_price_display_mode()

        subtotal_base = Decimal("0")  # Subtotal without tax (base prices)
        total_display_accumulated = Decimal("0")  # Sum of display prices (what user sees)

        items_count = 0
        for i, item in enumerate(items_data):
            try:
                menu_item_id = item.get("menu_item_id")
                _debug(f"Processing item {i + 1}: menu_item_id={menu_item_id}")

                menu_item = session.get(MenuItem, menu_item_id)
                if menu_item is None:
                    _debug(f"MenuItem {menu_item_id} NOT FOUND")
                    raise OrderValidationError(
                        f"Producto {menu_item_id} no encontrado",
                        status=HTTPStatus.BAD_REQUEST,
                    )

                quantity = int(item.get("quantity") or 1)
                if quantity <= 0:
                    quantity = 1

                # Get selected modifiers for this item
                selected_modifiers = item.get("modifiers") or []
                _debug(f"Selected modifiers for item {menu_item.name}: {selected_modifiers}")

                # Validate required modifiers (supports both dicts and IDs)
                validate_required_modifiers(session, menu_item.id, selected_modifiers)

                # Create order item with display price (as stored in DB)
                line_price = Decimal(menu_item.price)

                # Accumulate display price for tax-included fidelity
                total_display_accumulated += line_price * quantity

                order_item = OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=quantity,
                    unit_price=line_price,
                    special_instructions=item.get("special_instructions"),
                )
                session.add(order_item)
                session.flush()  # Flush to get order_item.id

                _debug(f"OrderItem created ID: {order_item.id}")

                # Calculate base price for this item (without tax)
                item_breakdown = calculate_price_breakdown(line_price, tax_decimal, price_mode)
                item_base_price = item_breakdown["price_base"] * quantity

                # Add modifiers to order item
                modifier_total_display = Decimal("0")
                modifier_total_base = Decimal("0")
                for selected_mod in selected_modifiers:
                    # Support both dict payloads and simple integer IDs
                    if isinstance(selected_mod, dict):
                        modifier_id = selected_mod.get("modifier_id")
                        mod_quantity = int(selected_mod.get("quantity", 1) or 1)
                    else:
                        modifier_id = int(selected_mod)
                        mod_quantity = 1

                    if not modifier_id:
                        continue

                    modifier = session.get(Modifier, modifier_id)
                    if modifier:
                        price_adjustment = Decimal(str(modifier.price_adjustment))

                        order_item_modifier = OrderItemModifier(
                            order_item=order_item,
                            modifier=modifier,
                            quantity=mod_quantity,
                            unit_price_adjustment=price_adjustment,
                        )
                        session.add(order_item_modifier)

                        # Calculate modifier prices
                        modifier_price = price_adjustment * mod_quantity
                        modifier_total_display += modifier_price
                        total_display_accumulated += modifier_price

                        # Calculate base price for modifiers
                        mod_breakdown = calculate_price_breakdown(
                            modifier_price, tax_decimal, price_mode
                        )
                        modifier_total_base += mod_breakdown["price_base"]

                # Add base prices to subtotal
                subtotal_base += item_base_price + modifier_total_base
                items_count += 1

            except Exception as item_err:
                _debug(f"Error processing item index {i}: {item_err}")
                raise

        if items_count == 0:
            _debug("CRITICAL: No items were processed successfully!")

        # Correctly calculate totals based on price mode
        if price_mode == "tax_included":
            # Trust the display sum as the total the user saw and expects
            total_amount = total_display_accumulated
            # Subtotal is the accumulated base price
            order.subtotal = subtotal_base
            # Tax is the difference (preserving total = subtotal + tax)
            tax_amount = total_amount - subtotal_base
        else:
            # Tax excluded: Base is truth, tax is added on top
            order.subtotal = subtotal_base
            tax_amount = (subtotal_base * tax_decimal).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_amount = subtotal_base + tax_amount

        order.tax_amount = tax_amount
        order.total_amount = total_amount
        order.tip_amount = Decimal("0")
        order.mark_status(OrderStatus.NEW.value)

        _debug(
            f"Order totals calculated: subtotal={subtotal_base}, tax={tax_amount}, total={total_amount}"
        )

        if cached_table_id:
            from pronto_shared.services.waiter_table_assignment_service import get_table_assignment

            try:
                assignment = get_table_assignment(cached_table_id)
                if assignment and assignment.get("waiter_id"):
                    waiter_id = assignment["waiter_id"]
                    order.waiter_id = waiter_id
                    order.accepted_at = datetime.utcnow()
                    order.waiter_accepted_at = datetime.utcnow()
                    order.mark_status(OrderStatus.QUEUED.value)

                    order_requires_kitchen = any(
                        not item.menu_item or not getattr(item.menu_item, "is_quick_serve", False)
                        for item in order.items
                    )
                    if not order_requires_kitchen:
                        order.ready_at = datetime.utcnow()
                        order.mark_status(OrderStatus.READY.value)
                        logger.info("Order %s auto-queued and marked ready (quick serve)", order.id)
                    else:
                        logger.info(
                            "Order %s auto-queued by waiter %s (table %s)",
                            order.id,
                            waiter_id,
                            cached_table_id,
                        )
            except Exception as assign_err:
                _debug(f"Error in waiter assignment: {assign_err}")

        if order.workflow_status == OrderStatus.CANCELLED.value:
            logger.warning("New order %s created with cancelled status; resetting to new", order.id)
            order.mark_status(OrderStatus.NEW.value)

        # Flush to ensure all objects are persisted before recomputing totals
        session.flush()

        # Save IDs using inspect to avoid triggering lazy loading on potentially expired instances
        from sqlalchemy import inspect as sqla_inspect

        order_id = sqla_inspect(order).identity[0] if sqla_inspect(order).identity else order.id
        session_id = (
            sqla_inspect(dining_session).identity[0]
            if sqla_inspect(dining_session).identity
            else dining_session.id
        )

        _debug("Before recompute_totals")

        # Pass the session explicitly to avoid lazy load issues
        dining_session.recompute_totals(db_session=session)

        _debug(f"Totals recomputed. Session total: {dining_session.total_amount}")

        # Commit to persist all changes
        session.commit()

        _debug("Transaction committed successfully")

        # Reconsult objects to get fresh instances with updated values
        order = session.get(Order, order_id)
        dining_session = session.get(DiningSession, session_id)

        # Emit notification for auto-accepted orders
        if order.waiter_id and order.workflow_status == OrderStatus.QUEUED.value:
            try:
                from pronto_shared.socketio_manager import emit_custom_event

                emit_custom_event(
                    "orders.auto_accepted",
                    {
                        "order_id": order.id,
                        "waiter_id": order.waiter_id,
                        "table_id": dining_session.table_id,
                        "table_number": dining_session.table_number,
                        "session_id": dining_session.id,
                    },
                    room=f"employee_{order.waiter_id}",
                )
            except Exception as emit_err:
                _debug(f"Error emitting auto_accepted event: {emit_err}")

        response = {
            "id": order.id,  # For consistency with API expectations
            "order_id": order.id,
            "session_id": dining_session.id,
            "order_status": order.workflow_status,
            "session_status": dining_session.status,
            "subtotal": float(order.subtotal),
            "tax_amount": float(order.tax_amount),
            "total_amount": float(order.total_amount),
            "session_total": float(dining_session.total_amount),
        }

        _debug("Returning success response")

        return response, HTTPStatus.CREATED


# =============================================================================
# TEST MANUAL PARA CONCURRENCIA (IntegrityError idx_dining_session_open_table)
# =============================================================================
#
# OBJETIVO: Verificar que el patrón get-or-create maneja race conditions
# correctamente cuando múltiples requests intentan crear sesiones para la misma mesa.
#
# PRUEBA A:
#   1) Disparar 10 requests concurrentes a POST /api/orders para misma mesa:
#      for i in {1..10}; do
#        curl -s -X POST http://localhost:6080/api/orders \
#          -H "Content-Type: application/json" \
#          -d '{"session_id":null,"table_id":1,"items":[{"menu_item_id":1,"quantity":1}],"customer":{"name":"Test","email":"audit@test.com"}}' &
#      done
#      wait
#
#   2) Verificar que NO haya IntegrityError en logs:
#      docker logs pronto-client --tail 100 | grep IntegrityError
#
#   3) Verificar que solo exista UNA sesión 'open' para table_id=1:
#      docker exec pronto-postgres psql -U pronto -d pronto -c \
#        "SELECT COUNT(*) FROM pronto_dining_sessions WHERE table_id=1 AND status='open';"
#
# EXPECTED: Sin errores IntegrityError, solo 1 sesión open por mesa
#
# PRUEBA B:
#   1) Disparar requests concurrentes a /api/sessions/open:
#      for i in {1..10}; do
#        curl -s -X POST http://localhost:6080/api/sessions/open \
#          -H "Content-Type: application/json" \
#          -d "{\"table_id\":1}" &
#      done
#      wait
#
#   2) Luego crear orden para esa mesa:
#      curl -s -X POST http://localhost:6080/api/orders \
#        -H "Content-Type: application/json" \
#        -d '{"items":[{"menu_item_id":1,"quantity":1}],"customer":{"name":"Test","email":"audit@test.com"}}'
#
# EXPECTED: Orden creada exitosamente, reusando la sesión existente
#
# NOTAS:
#   - El patrón get-or-create usa expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
#   - Si hay race condition, se hace session.rollback() y se re-consulta la sesión existente
#   - Los logs deben indicar "Reusing existing session", "Race condition detected", o "Recovered session"
#
# ============================================================================
