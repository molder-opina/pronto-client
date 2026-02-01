"""
Script to seed initial employee data and roles.
Can be run via `python3 -m bin.init.seed_employees`
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from shared.config import load_config
from shared.db import get_session, init_engine
from shared.services.seed import load_seed_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    try:
        logger.info("Initializing database connection...")
        config = load_config("seed_script")
        init_engine(config)

        logger.info("Starting employee seed...")
        with get_session() as session:
            # Force seed load which handles logic for creating/updating employees
            # and setting correct allow_scopes based on roles
            load_seed_data(session)
            session.commit()

        logger.info("Employee seed completed successfully!")

    except Exception as e:
        logger.error(f"Error seeding employees: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
