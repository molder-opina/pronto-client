"""
Price calculation service that handles different price display modes.

This service provides utilities to calculate prices correctly based on the
configured price display mode (tax included vs tax excluded).
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from flask import current_app

# Type alias for price display mode
PriceDisplayMode = Literal["tax_included", "tax_excluded"]


def get_price_display_mode() -> PriceDisplayMode:
    """
    Get the current price display mode from business config.

    Returns:
        'tax_included' or 'tax_excluded'
    """
    try:
        from shared.services.business_config_service import get_config_value

        mode = get_config_value("price_display_mode", "tax_included")
        if mode not in ["tax_included", "tax_excluded"]:
            current_app.logger.warning(
                f"Invalid price_display_mode '{mode}', defaulting to 'tax_included'"
            )
            return "tax_included"
        return mode
    except Exception as e:
        current_app.logger.error(f"Error getting price_display_mode: {e}", exc_info=True)
        return "tax_included"  # Safe default


def calculate_price_breakdown(
    display_price: Decimal, tax_rate: Decimal, mode: PriceDisplayMode | None = None
) -> dict[str, Decimal]:
    """
    Calculate price breakdown (base price, tax amount, final price) based on display mode.

    Args:
        display_price: The price as stored in the database (MenuItem.price or unit_price)
        tax_rate: The tax rate (e.g., 0.16 for 16%)
        mode: Price display mode. If None, will fetch from config.

    Returns:
        Dictionary with:
            - price_base: Price without tax
            - tax_amount: Tax amount
            - price_final: Final price (what customer pays)
            - display_price: What to show in menus/UI

    Examples:
        Mode 'tax_included' with display_price=116.00, tax_rate=0.16:
            price_base = 100.00
            tax_amount = 16.00
            price_final = 116.00
            display_price = 116.00

        Mode 'tax_excluded' with display_price=100.00, tax_rate=0.16:
            price_base = 100.00
            tax_amount = 16.00
            price_final = 116.00
            display_price = 100.00
    """
    if mode is None:
        mode = get_price_display_mode()

    display_price = Decimal(str(display_price))
    tax_rate = Decimal(str(tax_rate))

    if mode == "tax_included":
        # Price already includes tax
        # Calculate base price by removing tax: base = display / (1 + tax_rate)
        price_base = (display_price / (Decimal("1") + tax_rate)).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
        tax_amount = (display_price - price_base).quantize(Decimal("0.01"), ROUND_HALF_UP)
        price_final = display_price

    else:  # tax_excluded
        # Price does not include tax
        # Tax is added on top: tax = base * tax_rate
        price_base = display_price
        tax_amount = (display_price * tax_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        price_final = (price_base + tax_amount).quantize(Decimal("0.01"), ROUND_HALF_UP)

    return {
        "price_base": price_base,
        "tax_amount": tax_amount,
        "price_final": price_final,
        "display_price": display_price,
    }


def calculate_order_totals(
    items_subtotal: Decimal,
    tax_rate: Decimal,
    tip_amount: Decimal = Decimal("0"),
    mode: PriceDisplayMode | None = None,
) -> dict[str, Decimal]:
    """
    Calculate order totals based on items subtotal and tax rate.

    Important: The items_subtotal passed here should be the sum of price_base from all items,
    not the display prices.

    Args:
        items_subtotal: Sum of all items' base prices (without tax)
        tax_rate: Tax rate to apply
        tip_amount: Tip amount to add
        mode: Price display mode. If None, will fetch from config.

    Returns:
        Dictionary with:
            - subtotal: Items subtotal (base price, no tax)
            - tax_amount: Total tax
            - tip_amount: Tip amount
            - total_amount: Final total to pay
    """
    if mode is None:
        mode = get_price_display_mode()

    items_subtotal = Decimal(str(items_subtotal))
    tax_rate = Decimal(str(tax_rate))
    tip_amount = Decimal(str(tip_amount))

    # Tax is always calculated on the base price (subtotal)
    tax_amount = (items_subtotal * tax_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
    total_amount = (items_subtotal + tax_amount + tip_amount).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )

    return {
        "subtotal": items_subtotal,
        "tax_amount": tax_amount,
        "tip_amount": tip_amount,
        "total_amount": total_amount,
    }


def should_show_tax_indicator() -> bool:
    """
    Check if UI should show a "Prices + Tax" indicator.

    Returns:
        True if prices are shown without tax (tax_excluded mode)
    """
    return get_price_display_mode() == "tax_excluded"


def get_display_price_for_ui(
    stored_price: Decimal, tax_rate: Decimal, mode: PriceDisplayMode | None = None
) -> Decimal:
    """
    Get the price that should be displayed in the UI (menus, apps, etc.).

    Args:
        stored_price: The price stored in MenuItem.price
        tax_rate: Tax rate
        mode: Price display mode. If None, will fetch from config.

    Returns:
        The price to display in the UI
    """
    breakdown = calculate_price_breakdown(stored_price, tax_rate, mode)
    return breakdown["display_price"]


def get_item_total_price(
    unit_price: Decimal,
    quantity: int,
    modifiers_total: Decimal,
    tax_rate: Decimal,
    mode: PriceDisplayMode | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate the total price for an order item including modifiers.

    Args:
        unit_price: Unit price of the item (as stored in DB)
        quantity: Quantity ordered
        modifiers_total: Total price of all modifiers for this item
        tax_rate: Tax rate
        mode: Price display mode

    Returns:
        Tuple of (base_price, tax_amount, final_price)
    """
    if mode is None:
        mode = get_price_display_mode()

    # Calculate breakdown for the unit price
    item_breakdown = calculate_price_breakdown(unit_price, tax_rate, mode)

    # Calculate breakdown for modifiers
    modifiers_breakdown = calculate_price_breakdown(modifiers_total, tax_rate, mode)

    # Sum base prices
    base_price = (item_breakdown["price_base"] * quantity) + modifiers_breakdown["price_base"]

    # Calculate tax on total base
    tax_amount = (base_price * Decimal(str(tax_rate))).quantize(Decimal("0.01"), ROUND_HALF_UP)

    # Final price
    final_price = base_price + tax_amount

    return (
        base_price.quantize(Decimal("0.01"), ROUND_HALF_UP),
        tax_amount,
        final_price.quantize(Decimal("0.01"), ROUND_HALF_UP),
    )
