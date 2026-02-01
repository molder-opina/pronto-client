import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up path to import shared modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from shared.constants import OrderStatus, PaymentStatus
from shared.db import get_session, init_engine
from shared.models import Order


def verify_order():
    init_engine()
    with get_session() as session:
        order = session.query(Order).get(7)
        if order:
            logger.info(f"Order #7 Status: {order.workflow_status}")
            logger.info(f"Order #7 Payment: {order.payment_status}")
            logger.info(f"Order #7 ID: {order.id}")
        else:
            logger.warning("Order #7 not found")


if __name__ == "__main__":
    verify_order()
