import glob
import os
import sys
import logging

logger = logging.getLogger(__name__)

# Ensure we can import shared modules
sys.path.append("/opt/pronto")

try:
    from shared.config import AppConfig
    from shared.db import get_session, init_engine
    from shared.models import Order

    # Initialize DB
    class MockConfig:
        sqlalchemy_uri = ""  # implementation inside init_engine handles os.getenv('DATABASE_URL')

    init_engine(MockConfig())

    logger.info("--- ORDER VERIFICATION ---")
    with get_session() as session:
        order = session.query(Order).get(7)
        if order:
            logger.info(f"Order ID: {order.id}")
            logger.info(f"Status: {order.workflow_status}")
            logger.info(f"Payment: {order.payment_status}")
        else:
            logger.warning("Order #7 NOT FOUND")

except Exception as e:
    logger.error(f"DB Verification Failed: {e}")

logger.info("\n--- PDF VERIFICATION ---")
# Common paths for generated files
paths = ["/opt/pronto/static/pdfs", "/opt/pronto/static/receipts", "/tmp", "/var/tmp"]
found_pdfs = []
for p in paths:
    if os.path.exists(p):
        pdfs = glob.glob(os.path.join(p, "*.pdf"))
        found_pdfs.extend(pdfs)

if found_pdfs:
    logger.info(f"Found {len(found_pdfs)} PDF(s):")
    for pdf in found_pdfs:
        logger.info(f" - {pdf}")
else:
    logger.info("No PDFs found in common directories.")

logger.info("\n--- EMAIL VERIFICATION (Mock) ---")
# In this environment, we just check if the service is enabled/configured
logger.info(f"EMAIL_ENABLED: {os.environ.get('EMAIL_ENABLED')}")
