"""
Security helpers for hashing credentials and encrypting sensitive fields.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet


def normalize_identifier(value: str | None) -> str:
    """Normalize identifiers such as usernames or emails before hashing."""
    if not value:
        return ""
    return value.strip().lower()


def _get_salt() -> str:
    salt = os.getenv("PASSWORD_HASH_SALT")
    if salt:
        return salt
    raise RuntimeError(
        "PASSWORD_HASH_SALT environment variable not set. "
        "Please set this environment variable in production."
    )


def _derive_key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.getenv("CUSTOMER_DATA_KEY")
    if key:
        try:
            # Validate provided key is base64 urlsafe encoded.
            base64.urlsafe_b64decode(key)
            return Fernet(key.encode("utf-8"))
        except Exception:  # nosec B110
            # Fall back to derived key if the provided value is not valid.
            pass
    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "SECRET_KEY environment variable not set. "
            "Please set this environment variable in production."
        )
    derived = _derive_key_from_secret(secret)
    return Fernet(derived)


def _hash_payload(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_credentials(username: str | None, password: str | None) -> str:
    """
    Hash a username/password pair. Only the hash is stored; the raw values are discarded.
    """
    normalized_user = normalize_identifier(username)
    password = (password or "").strip()
    payload = f"{normalized_user}:{password}:{_get_salt()}"
    return _hash_payload(payload)


def verify_credentials(username: str | None, password: str | None, stored_hash: str) -> bool:
    """
    Compare a candidate username/password pair against the stored hash.
    """
    if not stored_hash:
        return False
    candidate = hash_credentials(username, password)
    return secrets.compare_digest(candidate, stored_hash)


def hash_identifier(value: str | None) -> str:
    """
    Hash arbitrary identifiers (e.g., emails) so they can be indexed without storing the raw value.
    """
    payload = f"{normalize_identifier(value)}:{_get_salt()}"
    return _hash_payload(payload)


def encrypt_string(value: str | None) -> str | None:
    """
    Encrypt a string using Fernet. Returns None when the input is None.
    """
    if value is None:
        return None
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_string(value: str | None) -> str | None:
    """
    Decrypt a previously encrypted string. Returns None when the input is None.
    """
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return None
