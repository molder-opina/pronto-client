"""
Utilities for waiter call data enrichment.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import DiningSession, Order


def get_waiter_assignment_from_session(
    dining_session: DiningSession | None,
) -> tuple[int | None, str | None]:
    """
    Extract the waiter assignment from a loaded DiningSession relationship.
    """
    if not dining_session or not dining_session.orders:
        return None, None

    for order in dining_session.orders:
        if order.waiter_id and order.waiter:
            return order.waiter_id, order.waiter.name

    return None, None


def get_waiter_assignment_from_db(
    db_session: Session,
    dining_session_id: int | None,
) -> tuple[int | None, str | None]:
    """
    Fetch the waiter assignment for a dining session directly from the database.
    """
    if not dining_session_id:
        return None, None

    order = (
        db_session.execute(
            select(Order)
            .where(Order.session_id == dining_session_id, Order.waiter_id.is_not(None))
            .order_by(Order.created_at.asc())
        )
        .scalars()
        .first()
    )

    if order and order.waiter_id and order.waiter:
        return order.waiter_id, order.waiter.name

    return None, None


def get_waiter_assignment_from_dining_session(
    dining_session: DiningSession | None,
) -> tuple[int | None, str | None]:
    """
    Backwards compatible wrapper kept for older modules that still import the
    previous helper name.
    """
    return get_waiter_assignment_from_session(dining_session)
