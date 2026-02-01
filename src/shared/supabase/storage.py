"""
Supabase Storage helper for uploads and file management.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

from supabase import Client, create_client

from shared.config import load_config

logger = logging.getLogger(__name__)


class SupabaseStorage:
    """Lightweight wrapper around Supabase Storage buckets."""

    _client: Client | None = None

    @classmethod
    def _get_client(cls) -> Client | None:
        if cls._client is None:
            try:
                config = load_config(os.getenv("APP_NAME", "pronto"))
                if not config.supabase_url or not config.supabase_service_role_key:
                    logger.warning(
                        "Supabase Storage credentials missing; falling back to local storage."
                    )
                    return None
                cls._client = create_client(config.supabase_url, config.supabase_service_role_key)
            except Exception as exc:
                logger.error("Failed to initialize Supabase Storage client: %s", exc)
                return None
        return cls._client

    @classmethod
    def is_available(cls) -> bool:
        """Check whether the Supabase client is ready for storage operations."""
        return cls._get_client() is not None

    @classmethod
    def upload_bytes(
        cls,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        client = cls._get_client()
        if client is None:
            raise RuntimeError("Supabase client not available")

        options: dict[str, Any] = {"upsert": True}
        if content_type:
            options["content-type"] = content_type

        response = client.storage.from_(bucket).upload(path, content, options)
        return response.model_dump() if hasattr(response, "model_dump") else {"data": response}

    @classmethod
    def delete_file(cls, bucket: str, path: str) -> bool:
        client = cls._get_client()
        if client is None:
            return False

        response = client.storage.from_(bucket).remove([path])
        if hasattr(response, "data"):
            return bool(response.data)
        return True

    @classmethod
    def list_files(cls, bucket: str, prefix: str) -> list[dict[str, Any]]:
        client = cls._get_client()
        if client is None:
            return []

        response = client.storage.from_(bucket).list(prefix)
        if hasattr(response, "data"):
            return response.data or []
        return response or []

    @classmethod
    def get_public_url(cls, bucket: str, path: str) -> str:
        config = load_config(os.getenv("APP_NAME", "pronto"))
        safe_path = quote(path, safe="/")
        return f"{config.supabase_url}/storage/v1/object/public/{bucket}/{safe_path}"


def resolve_bucket(category: str, config) -> str:
    """Map an image category to a bucket name."""
    normalized = (category or "menu").strip().lower()
    if normalized in {"profiles", "avatars", "staff"}:
        return config.storage_bucket_avatars
    if normalized in {"branding", "logos", "logo"}:
        return config.storage_bucket_logos
    return config.storage_bucket_menu
