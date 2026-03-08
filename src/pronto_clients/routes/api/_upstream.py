"""Helpers for resolving upstream API base URLs in client BFF proxies."""

from __future__ import annotations

import os


def get_pronto_api_base_url() -> str:
    """Resolve canonical BFF→API base URL for pronto-client."""
    return (
        (os.getenv("PRONTO_API_INTERNAL_BASE_URL") or "").strip()
        or (os.getenv("PRONTO_API_BASE_URL") or "").strip()
        or "http://localhost:6082"
    ).rstrip("/")
