"""
Factory for the customer-facing Flask application.

Uses Redis-backed customer_ref for authentication (not JWT).
Session Flask only stores: customer_ref, dining_session_id (allowlist AGENTS.md section 6).
"""

from __future__ import annotations

import os
import secrets
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import urlopen

from flask import Flask, jsonify, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from pronto_shared.extensions import csrf as csrf_protection
from pronto_clients.routes.api import api_bp
from pronto_clients.routes.web import web_bp

from pronto_shared.config import load_config
from pronto_shared.db import init_engine, validate_schema
from pronto_shared.error_handlers import register_error_handlers
from pronto_shared.logging_config import configure_logging
from pronto_shared.security_middleware import configure_security_headers
from pronto_shared.services.business_config_service import (
    sync_env_config_to_db,
)
from pronto_shared.services.secret_service import (
    load_env_secrets,
    sync_env_secrets_to_db,
)

# Using shared CSRF instance

_ROUTES_ONLY_ENV = "PRONTO_ROUTES_ONLY"
_CLIENT_ASSET_MANIFEST_CACHE: dict[str, object] = {
    "css_files": [],
    "fetched_at": 0.0,
}


def _is_routes_only() -> bool:
    return (os.getenv(_ROUTES_ONLY_ENV) or "").strip() == "1"


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")


def _build_static_upstream_candidates(app: Flask) -> list[str]:
    static_container_host = (
        app.config.get("PRONTO_STATIC_CONTAINER_HOST")
        or os.getenv("PRONTO_STATIC_CONTAINER_HOST")
        or ""
    ).rstrip("/")
    static_public_host = (
        app.config.get("PRONTO_STATIC_PUBLIC_HOST")
        or os.getenv("PRONTO_STATIC_PUBLIC_HOST")
        or ""
    ).rstrip("/")

    upstream_candidates: list[str] = []
    if static_container_host:
        upstream_candidates.append(static_container_host)

    for internal_host in ("http://static:80", "http://pronto-static-1:80"):
        if internal_host not in upstream_candidates:
            upstream_candidates.append(internal_host)

    if static_public_host:
        parsed_public = urlparse(static_public_host)
        public_host = (parsed_public.hostname or "").lower()
        if public_host in {"localhost", "127.0.0.1"}:
            host_docker = static_public_host.replace(
                parsed_public.netloc, f"host.docker.internal:{parsed_public.port or 80}"
            )
            if host_docker not in upstream_candidates:
                upstream_candidates.append(host_docker)
        elif static_public_host not in upstream_candidates:
            upstream_candidates.append(static_public_host)

    return upstream_candidates


def _resolve_client_vite_css_files(app: Flask) -> list[str]:
    now_ts = datetime.now(timezone.utc).timestamp()
    cached_css = _CLIENT_ASSET_MANIFEST_CACHE.get("css_files") or []
    fetched_at = float(_CLIENT_ASSET_MANIFEST_CACHE.get("fetched_at") or 0.0)

    # Refresh at most every 60s.
    if cached_css and (now_ts - fetched_at) < 60:
        return [str(css) for css in cached_css if css]

    manifest_path = "/assets/js/clients/.vite/manifest.json"
    for upstream_host in _build_static_upstream_candidates(app):
        target_url = f"{upstream_host}{manifest_path}"
        try:
            with urlopen(target_url, timeout=5) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                manifest = json.loads(raw)

                css_files: list[str] = []
                seen: set[str] = set()

                def _add_css_list(items: object) -> None:
                    if not isinstance(items, list):
                        return
                    for css_item in items:
                        css_rel = str(css_item or "").lstrip("/")
                        if not css_rel or css_rel in seen:
                            continue
                        seen.add(css_rel)
                        css_files.append(css_rel)

                for entry_key in ("entrypoints/base.ts",):
                    entry = manifest.get(entry_key) or {}
                    _add_css_list(entry.get("css"))
                    for import_key in entry.get("imports") or []:
                        import_entry = manifest.get(import_key) or {}
                        _add_css_list(import_entry.get("css"))

                if css_files:
                    _CLIENT_ASSET_MANIFEST_CACHE["css_files"] = css_files
                    _CLIENT_ASSET_MANIFEST_CACHE["fetched_at"] = now_ts
                    return css_files
        except Exception:
            continue

    _CLIENT_ASSET_MANIFEST_CACHE["fetched_at"] = now_ts
    return [str(css) for css in cached_css if css]


def init_runtime(app: Flask, config) -> None:
    init_engine(config)
    validate_schema()

    sync_env_secrets_to_db()
    sync_env_config_to_db()

    app.config["SECRET_KEY"] = config.secret_key
    app.config["PRONTO_STATIC_CONTAINER_HOST"] = config.pronto_static_container_host
    app.config["PRONTO_STATIC_PUBLIC_HOST"] = config.pronto_static_public_host
    app.config["APP_NAME"] = config.app_name
    app.config["TAX_RATE"] = config.tax_rate
    app.config["RESTAURANT_NAME"] = config.restaurant_name
    app.config["RESTAURANT_SLUG"] = config.restaurant_slug
    app.config["STRIPE_API_KEY"] = config.stripe_api_key

    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not config.debug_mode

    configure_security_headers(app)
    register_error_handlers(app)

    num_proxies = int(os.getenv("NUM_PROXIES", "0"))
    if num_proxies > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=num_proxies,
            x_proto=num_proxies,
            x_host=num_proxies,
            x_port=num_proxies,
        )

    # API Blueprints protected by CSRF (handled by frontend requestJSON wrapper)

    # Configure CORS with secure defaults
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    allowed_origins = (
        [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if raw_origins
        else []
    )
    if config.debug_mode and not allowed_origins:
        local_origin = os.getenv("PRONTO_CLIENT_PUBLIC_ORIGIN", "").strip()
        if local_origin:
            allowed_origins = [local_origin]
    if allowed_origins:
        CORS(
            app,
            resources={
                r"/api/*": {"origins": allowed_origins, "supports_credentials": True},
                r"/web/*": {"origins": allowed_origins, "supports_credentials": True},
            },
        )

    csrf_protection.init_app(app)

    @app.before_request
    def set_app_locale():
        """Set the global i18n locale from system settings."""
        from pronto_shared.i18n.service import i18n
        from pronto_shared.services.settings_service import get_setting

        locale = get_setting("system.locale.default", "es")
        i18n.set_locale(locale)

    @app.context_processor
    def inject_employees_base_url():
        base_url = (app.config.get("EMPLOYEE_API_BASE_URL") or "").rstrip("/")
        return {"employees_base_url": base_url}

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return jsonify(
            {
                "error": "CSRF Error",
                "details": e.description,
            }
        ), 400

    @app.context_processor
    def inject_globals():
        from pronto_shared.services.settings_service import get_setting

        app_settings = {
            "static_host_url": config.pronto_static_public_host,
            "currency_code": get_setting("currency_code", "MXN"),
            "currency_locale": get_setting("currency_locale", "es-MX"),
            "currency_symbol": get_setting("currency_symbol", "$"),
            "default_country_code": get_setting("default_country_code", "+52"),
            "phone_country_options": get_setting("phone_country_options")
            or [
                {"iso": "MX", "label": "Mexico", "dial_code": "+52", "flag": ""},
            ],
            "checkout_default_method": get_setting("checkout_default_method", "cash"),
            "checkout_redirect_seconds": int(
                get_setting("client.checkout.redirect_seconds", 6)
            ),
            "waiter_call_sound": get_setting("waiter_call_sound", "bell1.mp3"),
            "waiter_call_cooldown_seconds": int(
                get_setting("waiter.call_cooldown_seconds", 60)
            ),
        }

        from pronto_shared.services.customer_session_store import (
            customer_session_store,
            RedisUnavailableError,
        )
        from pronto_shared.trazabilidad import get_logger

        customer_ref = session.get("customer_ref")
        current_user = None
        if customer_ref:
            try:
                current_user = customer_session_store.get_customer(customer_ref)
            except RedisUnavailableError:
                logger = get_logger("clients")
                logger.warning("Customer session store (Redis) is unavailable.")
                current_user = None
            except Exception as e:
                logger = get_logger("clients")
                logger.error(
                    f"An unexpected error occurred fetching customer session: {e}",
                    error={"type": type(e).__name__, "message": str(e)},
                )
                current_user = None

        base_url = config.pronto_static_public_host
        assets_path = config.static_assets_path
        restaurant_slug = config.restaurant_slug

        return {
            "app_name": config.app_name,
            "system_version": config.system_version,
            "static_host_url": base_url,
            "restaurant_name": get_setting("restaurant_name", config.restaurant_name),
            "restaurant_assets": f"{base_url}{assets_path}/{restaurant_slug}",
            "current_year": datetime.now(timezone.utc).year,
            "debug_mode": config.debug_mode,
            "show_estimated_time": get_setting("orders.show_estimated_time", True),
            "estimated_time_min": get_setting("orders.estimated_time_min", 25),
            "estimated_time_max": get_setting("orders.estimated_time_max", 30),
            "app_settings": app_settings,
            "employee_api_base_url": app.config.get("EMPLOYEE_API_BASE_URL"),
            "current_user": current_user,
            "customer_id": current_user.get("customer_id") if current_user else None,
            "customer_name": current_user.get("name") if current_user else None,
            "session_id": session.get("dining_session_id"),
            "table_id": None,
            "assets_css": f"{base_url}{assets_path}/css",
            "assets_css_shared": f"{base_url}{assets_path}/css/shared",
            "assets_css_clients": f"{base_url}{assets_path}/css/clients",
            "assets_js": f"{base_url}{assets_path}/js",
            "assets_js_shared": f"{base_url}{assets_path}/js/shared",
            "assets_js_clients": f"{base_url}{assets_path}/js/clients",
            "assets_lib": f"{base_url}{assets_path}/lib",
            "assets_images": f"{base_url}{assets_path}/images",
            "client_vite_css_files": [
                f"{base_url}{assets_path}/js/clients/{css_rel.lstrip('/')}"
                for css_rel in _resolve_client_vite_css_files(app)
            ],
        }


def create_app() -> Flask:
    """
    Build and configure the Flask app for clients.
    """
    routes_only = _is_routes_only()

    if not routes_only:
        load_env_secrets()

        # Validate all required environment variables (fail-fast)
        from pronto_shared.config import validate_required_env_vars

        validate_required_env_vars(skip_in_debug=False)

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder=None,
    )
    register_blueprints(app)

    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "pronto-client",
                "version": app.config.get("SYSTEM_VERSION")
                or os.getenv("PRONTO_SYSTEM_VERSION", "1.0000"),
            }
        ), 200

    if routes_only:
        # Use env var or generate a random secret for routes-only mode
        # Random secret is fine for unit tests where session persistence doesn't matter
        app.config["SECRET_KEY"] = os.getenv("PRONTO_ROUTES_SECRET") or secrets.token_hex(32)
        return app

    config = load_config("pronto-clients")
    configure_logging(config.app_name, config.log_level)

    app.config["SYSTEM_VERSION"] = config.system_version
    app.config["DEBUG_MODE"] = config.debug_mode
    app.config["DEBUG"] = config.flask_debug
    app.config["DEBUG_AUTO_TABLE"] = config.debug_auto_table
    app.config["AUTO_READY_QUICK_SERVE"] = config.auto_ready_quick_serve
    app.config["EMPLOYEE_API_BASE_URL"] = (
        os.getenv("EMPLOYEE_API_BASE_URL")
        or os.getenv("PRONTO_EMPLOYEES_BASE_URL")
        or ""
    ).strip()

    # Browser must use same-origin /api/* and rely on the client BFF proxy.
    # Do not expose PRONTO_API_BASE_URL (often localhost:6082) to the browser,
    # otherwise remote devices resolve localhost incorrectly and fail with
    # "Error de conexión" on client page load.
    app.config["API_BASE_URL"] = ""

    init_runtime(app, config)

    return app


app = create_app()
