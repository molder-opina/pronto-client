"""
Utilities to centralize configuration handling across the pronto services.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class AppConfig:
    """Simple container for application level settings."""

    app_name: str
    # PostgreSQL/Supabase database
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    db_sslmode: str
    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    # Storage
    storage_bucket_avatars: str
    storage_bucket_menu: str
    storage_bucket_logs: str
    # Static content configuration (URLs HTTP)
    pronto_static_container_host: str
    nginx_host: str
    nginx_port: int
    static_assets_path: str
    # App settings
    secret_key: str
    log_level: str
    restaurant_name: str
    restaurant_slug: str
    tax_rate: float
    stripe_api_key: str
    debug_mode: bool
    flask_debug: bool
    debug_auto_table: bool
    auto_ready_quick_serve: bool
    # JWT settings
    jwt_access_token_expires_hours: int
    jwt_refresh_token_expires_days: int

    def get_bool(self, key: str, default: bool = False) -> bool:
        """
        Get boolean config value from AppConfig.

        Args:
            key: Configuration key (e.g., 'feedback_prompt_enabled')
            default: Default value if not set (defaults to False)

        Returns:
            bool: Configuration value
        """
        value = getattr(self, key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_int(self, key: str, default: int = 0) -> int:
        """
        Get integer config value from AppConfig.

        Args:
            key: Configuration key (e.g., 'feedback_prompt_timeout_seconds')
            default: Default value if not set (defaults to 0)

        Returns:
            int: Configuration value
        """
        value = getattr(self, key, default)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return value if isinstance(value, int) else default

    def get_string(self, key: str, default: str = "") -> str:
        """
        Get string config value from AppConfig.

        Args:
            key: Configuration key (e.g., 'feedback_email_subject')
            default: Default value if not set (defaults to empty string)

        Returns:
            str: Configuration value
        """
        value = getattr(self, key, default)
        return str(value) if value is not None else default

    @property
    def sqlalchemy_uri(self) -> str:
        """
        Build a SQLAlchemy PostgreSQL URI using psycopg2 as the driver.

        The format is compatible with SQLAlchemy's engine URL expectations.
        Includes SSL mode for Supabase connections.
        """
        ssl_arg = f"?sslmode={self.db_sslmode}" if self.db_sslmode else ""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}{ssl_arg}"
        )


def _read_env(name: str, default: str | None = None) -> str:
    """
    Internal helper to fetch environment variables with support for defaults.
    """
    value = os.getenv(name)
    if value is None:
        if default is None:
            raise RuntimeError(f"Missing required environment variable '{name}'")
        value = default
    return value


def read_bool(name: str, default: str = "false") -> bool:
    value = _read_env(name, default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def validate_required_env_vars(skip_in_debug: bool = False) -> None:
    """
    Validate that all required environment variables are set.

    This function checks for critical environment variables that must be
    configured for the application to function properly. It's designed to
    fail fast during startup rather than encountering errors later.

    Args:
        skip_in_debug: If True, skip validation when DEBUG_MODE=true

    Raises:
        RuntimeError: If any required variable is missing or has an invalid value
    """
    # Skip validation in debug mode if requested
    if skip_in_debug and read_bool("DEBUG_MODE", "false"):
        return

    errors = []
    warnings = []

    # Critical security variables
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key or secret_key in [
        "change-me-please",
        "super-secret-change-me",
        "your-secret-key-here",
    ]:
        errors.append(
            "SECRET_KEY must be configured with a secure random value. "
            'Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    handoff_pepper = os.getenv("HANDOFF_PEPPER", "")
    if not handoff_pepper or handoff_pepper == "your-random-pepper-here-32chars-minimum":
        errors.append(
            "HANDOFF_PEPPER must be configured with a secure random value. "
            'Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    password_salt = os.getenv("PASSWORD_HASH_SALT", "")
    if not password_salt or password_salt in [
        "super-secure-salt",
        "your-password-hash-salt-here-32chars-minimum",
    ]:
        errors.append(
            "PASSWORD_HASH_SALT must be configured with a secure random value. "
            'Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    customer_key = os.getenv("CUSTOMER_DATA_KEY", "")
    if not customer_key or customer_key == "your-customer-data-encryption-key-here-32chars-minimum":
        errors.append(
            "CUSTOMER_DATA_KEY must be configured with a secure random value. "
            'Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    # Database configuration
    postgres_host = os.getenv("POSTGRES_HOST", "")
    if not postgres_host:
        errors.append("POSTGRES_HOST must be configured")

    postgres_user = os.getenv("POSTGRES_USER", "")
    if not postgres_user:
        errors.append("POSTGRES_USER must be configured")

    postgres_password = os.getenv("POSTGRES_PASSWORD", "")
    if not postgres_password:
        errors.append("POSTGRES_PASSWORD must be configured")

    postgres_db = os.getenv("POSTGRES_DB", "")
    if not postgres_db:
        errors.append("POSTGRES_DB must be configured")

    # JWT configuration
    jwt_access_hours = os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "")
    if jwt_access_hours:
        try:
            hours = int(jwt_access_hours)
            if hours < 1 or hours > 168:  # 1 hour to 7 days
                warnings.append(
                    f"JWT_ACCESS_TOKEN_EXPIRES_HOURS={hours} is outside recommended range (1-168 hours)"
                )
        except ValueError:
            errors.append(
                f"JWT_ACCESS_TOKEN_EXPIRES_HOURS must be a valid integer, got: {jwt_access_hours}"
            )

    jwt_refresh_days = os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "")
    if jwt_refresh_days:
        try:
            days = int(jwt_refresh_days)
            if days < 1 or days > 90:  # 1 day to 90 days
                warnings.append(
                    f"JWT_REFRESH_TOKEN_EXPIRES_DAYS={days} is outside recommended range (1-90 days)"
                )
        except ValueError:
            errors.append(
                f"JWT_REFRESH_TOKEN_EXPIRES_DAYS must be a valid integer, got: {jwt_refresh_days}"
            )

    # Raise errors if any
    if errors:
        error_msg = "\n❌ Configuration Errors - Missing or invalid environment variables:\n"
        for error in errors:
            error_msg += f"  - {error}\n"
        error_msg += (
            "\nPlease check your config/secrets.env file and ensure all required variables are set."
        )
        raise RuntimeError(error_msg)


def load_config(app_name: str) -> AppConfig:
    """
    Produce an AppConfig instance populated from environment variables.

    Each micro-service passes its desired `app_name` to keep logs and traces easy
    to differentiate while still reusing the same config loader.

    Supports both Supabase (remote) and local PostgreSQL.
    Set USE_LOCAL_POSTGRES=true to use local PostgreSQL instead of Supabase.
    """
    return AppConfig(
        app_name=app_name,
        # PostgreSQL database (local container)
        db_host=_read_env("POSTGRES_HOST", "pronto-postgres"),
        db_port=int(_read_env("POSTGRES_PORT", "5432")),
        db_user=_read_env("POSTGRES_USER", "pronto"),
        db_password=_read_env("POSTGRES_PASSWORD", "pronto"),
        db_name=_read_env("POSTGRES_DB", "pronto"),
        db_sslmode=_read_env("POSTGRES_SSLMODE", "disable"),
        # Supabase (Optional/Legacy - moved to separate module)
        supabase_url=_read_env("SUPABASE_URL", ""),
        supabase_anon_key=_read_env("SUPABASE_ANON_KEY", ""),
        supabase_service_role_key=_read_env("SUPABASE_SERVICE_ROLE_KEY", ""),
        # Storage
        storage_bucket_avatars=_read_env("STORAGE_BUCKET_AVATARS", "customer-avatars"),
        storage_bucket_menu=_read_env("STORAGE_BUCKET_MENU", "menu-images"),
        storage_bucket_logs=_read_env("STORAGE_BUCKET_LOGS", "business-logos"),
        # Static content configuration (URLs HTTP)
        pronto_static_container_host=_read_env(
            "PRONTO_STATIC_CONTAINER_HOST", "http://localhost:9088"
        ),
        nginx_host=_read_env("NGINX_HOST", "static"),
        nginx_port=int(_read_env("NGINX_PORT", "80")),
        static_assets_path=_read_env("STATIC_ASSETS_PATH", "/assets"),
        # App settings
        secret_key=_read_env("SECRET_KEY", "super-secret-change-me"),
        log_level=_read_env("LOG_LEVEL", "INFO"),
        restaurant_name=_read_env("RESTAURANT_NAME", "pronto"),
        restaurant_slug=_slugify(_read_env("RESTAURANT_NAME", "pronto")),
        tax_rate=float(_read_env("TAX_RATE", "0.16")),
        stripe_api_key=_read_env("STRIPE_API_KEY", ""),
        debug_mode=read_bool("DEBUG_MODE", "false"),
        flask_debug=read_bool("FLASK_DEBUG", "false"),
        debug_auto_table=read_bool("DEBUG_AUTO_TABLE", "false"),
        auto_ready_quick_serve=read_bool("AUTO_READY_QUICK_SERVE", "false"),
        # JWT settings
        jwt_access_token_expires_hours=int(_read_env("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "24")),
        jwt_refresh_token_expires_days=int(_read_env("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7")),
    )


# Session TTL for anonymous client sessions (in hours)
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "4"))

# Enable takeaway/remote ordering feature
ENABLE_TAKEAWAY = os.getenv("ENABLE_TAKEAWAY", "false").lower() == "true"
