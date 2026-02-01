"""
Datetime utilities with Python 3.10+ compatibility.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Get current UTC time (timezone-aware).

    Compatible con Python 3.10+ (usa timezone.utc en lugar de UTC).
    """
    return datetime.now(timezone.utc)
