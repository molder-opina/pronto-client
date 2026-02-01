"""
Patch for psycopg2-binary 2.9.11 issue with PG type 1043 (character varying)

This module patches psycopg2 to handle unknown types gracefully.
"""

import logging

logger = logging.getLogger(__name__)

# Patch psycopg2 to ignore unknown types instead of raising error
try:
    from psycopg2 import _psycopg

    # Store original _make_oid
    original_make_oid = _psycopg._make_oid

    # Create patched version that returns STRING for type 1043 (varchar)
    def patched_make_oid(oid, conn):
        """Return STRING for unknown OIDs to prevent errors."""
        if oid == 1043:  # character varying / varchar
            # Return a simple string type instead of raising error
            logger.debug(f"Handling unknown OID {oid} as STRING")
            return _psycopg.STRING
        # For other unknown types, return NULL to prevent crashes
        try:
            return original_make_oid(oid, conn)
        except KeyError:
            logger.warning(f"Unknown PostgreSQL OID: {oid}, returning NULL")
            return None

    # Apply patch
    _psycopg._make_oid = patched_make_oid
    logger.info("Applied psycopg2 patch for unknown types")

except Exception as e:
    logger.warning(f"Could not apply psycopg2 patch: {e}")
