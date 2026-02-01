"""
Order cancellation service - shared between client and employee apps.
"""

from http import HTTPStatus

from shared.logging_config import get_logger
from shared.services.order_service import cancel_order as transition_cancel_order

logger = get_logger(__name__)


def cancel_order(
    order_id: int,
    actor: str = "employee",
    *,
    session_id: int | None = None,
    reason: str | None = None,
) -> tuple[dict, HTTPStatus]:
    """Cancel an order via the policy engine."""
    actor_scope = actor
    if actor_scope in {"customer", "client"}:
        actor_scope = "client"
    if actor_scope == "employee":
        actor_scope = "waiter"

    response, status = transition_cancel_order(
        order_id=order_id,
        actor_scope=actor_scope,
        session_id=session_id,
        reason=reason,
    )
    if status == HTTPStatus.OK:
        logger.info("Order %s cancelled by %s", order_id, actor_scope)
    return response, status
