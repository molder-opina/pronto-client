"""
Factory for employee-facing Flask dashboard.

Uses JWT for authentication instead of server-side sessions.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from shared.extensions import csrf
from flask import Flask, redirect, render_template, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.audit_middleware import init_audit_middleware
from shared.config import load_config
from shared.db import get_session, init_db, init_engine
from shared.error_handlers import register_error_handlers
from shared.jwt_middleware import (
    apply_jwt_scope_guard,
    get_active_scope,
    get_current_user,
    init_jwt_middleware,
)
from shared.logging_config import configure_logging
from shared.models import Base
from shared.permissions import Permission, get_permissions_for_role, has_permission
from shared.security_middleware import configure_security_headers
from shared.services.business_config_service import get_config_map, sync_env_config_to_db
from shared.services.image_service import ImageService
from shared.services.secret_service import load_env_secrets, sync_env_secrets_to_db
from shared.services.seed import ensure_seed_data, load_seed_data

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Build the Flask application that powers the employee portal.
    """
    load_env_secrets()
    app_root = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )

    # Initialize Audit Middleware Standard
    init_audit_middleware(app)

    # Validate all required environment variables (fail-fast)
    from shared.config import validate_required_env_vars, read_bool

    validate_required_env_vars(skip_in_debug=False)

    config = load_config("pronto-employees")

    configure_logging(config.app_name, config.log_level)

    # Initialize database engine first (before any DB queries)
    init_engine(config)
    init_db(Base.metadata)

    sync_env_secrets_to_db()

    app.config["SECRET_KEY"] = config.secret_key
    app.config["PRONTO_STATIC_CONTAINER_HOST"] = config.pronto_static_container_host
    app.config["APP_NAME"] = config.app_name
    app.config["TAX_RATE"] = config.tax_rate
    app.config["RESTAURANT_NAME"] = config.restaurant_name
    app.config["RESTAURANT_SLUG"] = config.restaurant_slug
    app.config["STRIPE_API_KEY"] = config.stripe_api_key
    app.config["CURRENCY"] = os.getenv("CURRENCY", "MXN")
    app.config["CURRENCY_SYMBOL"] = os.getenv("CURRENCY_SYMBOL", "$")

    # Initialize JWT middleware
    init_jwt_middleware(app)

    app.config["DEBUG_MODE"] = config.debug_mode
    app.config["DEBUG"] = config.flask_debug
    app.config["AUTO_READY_QUICK_SERVE"] = config.auto_ready_quick_serve
    static_assets_root = os.getenv(
        "STATIC_ASSETS_ROOT", str(Path(__file__).resolve().parents[2] / "static_content" / "assets")
    )
    app.config["STATIC_ASSETS_ROOT"] = static_assets_root
    ImageService.UPLOAD_FOLDER = static_assets_root
    ImageService.RESTAURANT_SLUG = config.restaurant_slug

    configure_security_headers(app)
    register_error_handlers(app)

    # ProxyFix: Trust X-Forwarded-* headers from reverse proxy
    num_proxies = int(os.getenv("NUM_PROXIES", "0"))
    if num_proxies > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=num_proxies,
            x_proto=num_proxies,
            x_host=num_proxies,
            x_port=num_proxies,
        )

    with get_session() as session:
        # Load seed data if LOAD_SEED_DATA=true (UPSERT mode)
        if read_bool("LOAD_SEED_DATA", "false"):
            logger.info("[SEED] Loading seed data using UPSERT mode (load_seed_data)...")
            load_seed_data(session)
            session.commit()
            logger.info("[SEED] Seed data loaded successfully!")
        else:
            logger.info("[SEED] Using legacy mode (ensure_seed_data) - only loads if DB is empty")
            ensure_seed_data(session)

    sync_env_config_to_db()

    business_settings = get_config_map(["currency_code", "currency_symbol"])
    if business_settings.get("currency_code"):
        app.config["CURRENCY"] = business_settings["currency_code"]
    if business_settings.get("currency_symbol"):
        app.config["CURRENCY_SYMBOL"] = business_settings["currency_symbol"]

    # CSRF Protection configuration (BEFORE registering blueprints)
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour CSRF token validity
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False

    csrf.init_app(app)

    # Register blueprints
    from routes.admin.auth import admin_bp
    from routes.api import api_bp
    from routes.api_scoped import register_scoped_apis
    from routes.auth import auth_bp
    from routes.cashier.auth import cashier_bp
    from routes.chef.auth import chef_bp
    from routes.dashboard import dashboard_bp
    from routes.system.auth import system_bp
    from routes.waiter.auth import waiter_bp

    # Register auth and dashboard first (used by templates)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    # Register context-aware blueprints
    app.register_blueprint(system_bp)
    app.register_blueprint(waiter_bp)
    app.register_blueprint(chef_bp)
    app.register_blueprint(cashier_bp)
    app.register_blueprint(admin_bp)

    # Register legacy /api/* routes (no scope validation)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Register scoped /<scope>/api/* routes (with scope validation)
    register_scoped_apis(app, api_bp)

    # Exempt API routes from CSRF
    api_blueprint_names = ["api"] + [
        f"{s}_api" for s in ["waiter", "chef", "cashier", "admin", "system"]
    ]
    for name in list(app.blueprints.keys()):
        if any(
            name == bp_name or name.startswith(f"{bp_name}.") for bp_name in api_blueprint_names
        ):
            try:
                csrf.exempt(name)
            except Exception:
                pass

    # Apply JWT scope guard middleware (validates URL scope == JWT scope)
    apply_jwt_scope_guard(app)

    # Configure CORS with secure defaults
    allowed_origins = (
        os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if os.getenv("CORS_ALLOWED_ORIGINS")
        else []
    )
    if config.debug_mode or not allowed_origins:
        allowed_origins = [
            "http://localhost:6081",
            "http://localhost:6080",
            "http://127.0.0.1:6081",
            "http://127.0.0.1:6080",
        ]
        CORS(
            app,
            resources={
                r"/api/*": {"origins": allowed_origins, "supports_credentials": True},
            },
            supports_credentials=True,
        )
    else:
        CORS(
            app,
            resources={
                r"/api/*": {"origins": allowed_origins, "supports_credentials": True},
            },
            supports_credentials=True,
        )

    # Custom Jinja2 filter to use HTTPS only for non-localhost URLs
    @app.template_filter("to_https")
    def to_https(url: str) -> str:
        if not url or url.startswith("https://"):
            return url
        if "localhost" in url.lower() or "127.0.0.1" in url:
            return url.replace("https://", "http://")
        return url

    # Selective security headers for sensitive routes
    @app.after_request
    def set_selective_security_headers(response):
        path = request.path

        is_sensitive = (
            path.startswith("/system/")
            or path.endswith("/super_admin_login")
            or path.endswith("/login")
            or path.endswith("/reauth")
        )

        if is_sensitive:
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["Vary"] = "Cookie"

        return response

    @app.route("/")
    @app.route("/console")
    def index():
        """Root route - show console selector directly."""
        return render_template(
            "console_selector.html", employee_name="Usuario", employee_role="guest"
        )

    @app.route("/test-console")
    def test_console():
        """Test route for console selector."""
        return "<!DOCTYPE html><html><head><title>Test Console</title></head><body><h1>Console Selector</h1><p>Employee: Usuario</p><p>Role: guest</p></body></html>"

    @app.route("/test-template")
    def test_template():
        """Test template rendering."""
        return render_template(
            "console_selector.html", employee_name="Usuario", employee_role="guest"
        )

    @app.context_processor
    def inject_globals():
        current_user = get_current_user()

        config_keys = [
            "currency_code",
            "currency_symbol",
            "currency_locale",
            "checkout_default_method",
            "checkout_prompt_duration_seconds",
            "paid_orders_window_minutes",
            "realtime_poll_interval_ms",
            "waiter_notification_timeout",
        ]
        business_map = get_config_map(config_keys)
        app_settings = {
            "currency_code": business_map.get("currency_code", app.config.get("CURRENCY", "MXN")),
            "currency_symbol": business_map.get(
                "currency_symbol", app.config.get("CURRENCY_SYMBOL", "$")
            ),
            "currency_locale": business_map.get("currency_locale", "es-MX"),
            "checkout_default_method": business_map.get("checkout_default_method", "cash"),
            "checkout_prompt_duration_seconds": int(
                business_map.get("checkout_prompt_duration_seconds", 6) or 6
            ),
            "paid_orders_window_minutes": int(
                business_map.get("paid_orders_window_minutes", 15) or 15
            ),
            "realtime_poll_interval_ms": int(
                business_map.get("realtime_poll_interval_ms", 1000) or 1000
            ),
            "waiter_notification_timeout": int(
                business_map.get("waiter_notification_timeout", 3000) or 3000
            ),
        }

        # Get user info from JWT
        employee_id = current_user.get("employee_id") if current_user else None
        employee_name = current_user.get("employee_name") if current_user else None
        employee_email = current_user.get("employee_email") if current_user else None
        employee_role = current_user.get("employee_role") if current_user else None
        active_scope = current_user.get("active_scope") if current_user else "admin"

        base_url = config.pronto_static_container_host
        assets_path = config.static_assets_path
        restaurant_slug = config.restaurant_slug

        return {
            "app_name": config.app_name,
            "restaurant_name": config.restaurant_name,
            "restaurant_assets": f"{base_url}{assets_path}/{restaurant_slug}",
            "current_year": datetime.utcnow().year,
            "debug_mode": config.debug_mode,
            "currency": app_settings["currency_code"],
            "currency_symbol": app_settings["currency_symbol"],
            "app_settings": app_settings,
            # Global variables for dashboard.html (from JWT)
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_role": employee_role,
            "role_capabilities": [p.value for p in get_permissions_for_role(employee_role or "")],
            "can_process_payments": has_permission(
                employee_role or "", Permission.PAYMENTS_PROCESS
            ),
            "items_per_page": int(business_map.get("items_per_page", 10) or 10),
            "paid_orders_retention_minutes": app_settings["paid_orders_window_minutes"],
            "payment_action_delay_seconds": app_settings["checkout_prompt_duration_seconds"],
            "table_base_prefix": business_map.get("table_base_prefix", "M"),
            "current_user": {
                "id": employee_id,
                "name": employee_name,
                "email": employee_email,
                "role": employee_role,
                "permissions": [p.value for p in get_permissions_for_role(employee_role or "")],
            }
            if employee_id
            else None,
            "has_permission": lambda p: has_permission(employee_role or "", p),
            "app_context": active_scope,
            "Permission": Permission,
            # Static assets URLs (short variables)
            "assets_css": f"{base_url}{assets_path}/css",
            "assets_css_employees": f"{base_url}{assets_path}/css/employees",
            "assets_js": f"{base_url}{assets_path}/js",
            "assets_js_employees": f"{base_url}{assets_path}/js/employees",
            "assets_images": f"{base_url}{assets_path}/pronto",
        }

    return app


app = create_app()
