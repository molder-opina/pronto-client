"""
Factory for the customer-facing Flask application.

Uses JWT for authentication instead of server-side sessions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from pronto_shared.extensions import csrf as csrf_protection
from pronto_clients.routes.api import api_bp
from pronto_clients.routes.web import web_bp

from pronto_shared.config import load_config
from pronto_shared.db import init_db, init_engine
from pronto_shared.error_handlers import register_error_handlers
from pronto_shared.jwt_middleware import init_jwt_middleware
from pronto_shared.logging_config import configure_logging
from pronto_shared.models import Base
from pronto_shared.security_middleware import configure_security_headers
from pronto_shared.services.business_config_service import (
    get_config_map,
    sync_env_config_to_db,
)
from pronto_shared.services.secret_service import (
    load_env_secrets,
    sync_env_secrets_to_db,
)

# Using shared CSRF instance


def create_app() -> Flask:
    """
    Build and configure the Flask app for clients.
    """
    load_env_secrets()

    # Validate all required environment variables (fail-fast)
    from pronto_shared.config import validate_required_env_vars

    validate_required_env_vars(skip_in_debug=False)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    pronto_static_root = os.path.abspath(
        os.path.join(repo_root, "..", "pronto-static", "src", "static_content", "assets")
    )
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    config = load_config("pronto-clients")

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

    # CSRF Protection configuration
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour CSRF token validity

    # Initialize JWT middleware
    init_jwt_middleware(app)

    app.config["DEBUG_MODE"] = config.debug_mode
    app.config["DEBUG"] = config.flask_debug
    app.config["DEBUG_AUTO_TABLE"] = config.debug_auto_table
    app.config["AUTO_READY_QUICK_SERVE"] = config.auto_ready_quick_serve
    app.config["EMPLOYEE_API_BASE_URL"] = os.getenv("PRONTO_EMPLOYEES_BASE_URL", "").strip()

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

    sync_env_config_to_db()

    # Explicitly exempt nested blueprints from CSRF
    from pronto_clients.routes.api.auth import auth_bp
    from pronto_clients.routes.api.feedback import feedback_bp
    from pronto_clients.routes.api.orders import orders_bp
    from pronto_clients.routes.api.payments import payments_bp
    from pronto_clients.routes.api.sessions import sessions_bp
    from pronto_clients.routes.api.stripe_payments import stripe_payments_bp

    csrf_protection.exempt(api_bp)
    csrf_protection.exempt(auth_bp)
    csrf_protection.exempt(orders_bp)
    csrf_protection.exempt(stripe_payments_bp)
    csrf_protection.exempt(sessions_bp)
    csrf_protection.exempt(feedback_bp)
    csrf_protection.exempt(payments_bp)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    # Configure CORS with secure defaults
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    allowed_origins = (
        [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if raw_origins
        else []
    )
    if config.debug_mode or not allowed_origins:
        allowed_origins = [
            "http://localhost:6080",
            "http://127.0.0.1:6080",
        ]
        CORS(
            app,
            resources={
                r"/api/*": {"origins": allowed_origins, "supports_credentials": True},
                r"/web/*": {"origins": allowed_origins, "supports_credentials": True},
            },
        )
    else:
        CORS(
            app,
            resources={
                r"/api/*": {"origins": allowed_origins, "supports_credentials": True},
                r"/web/*": {"origins": allowed_origins, "supports_credentials": True},
            },
            supports_credentials=True,
        )

    csrf_protection.init_app(app)

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
                "diagnosis": "Server Reloaded on new handler",
            }
        ), 400

    @app.context_processor
    def inject_globals():
        from pronto_shared.services.settings_service import get_setting

        config_keys = [
            "currency_code",
            "currency_locale",
            "currency_symbol",
            "default_country_code",
            "phone_country_options",
            "checkout_default_method",
            "checkout_prompt_duration_seconds",
            "waiter_call_sound",
            "waiter_call_cooldown_seconds",
        ]
        business_settings = get_config_map(config_keys)
        app_settings = {
            "currency_code": business_settings.get("currency_code", "MXN"),
            "currency_locale": business_settings.get("currency_locale", "es-MX"),
            "currency_symbol": business_settings.get("currency_symbol", "$"),
            "default_country_code": business_settings.get("default_country_code", "+52"),
            "phone_country_options": business_settings.get("phone_country_options")
            or [
                {"iso": "MX", "label": "Mexico", "dial_code": "+52", "flag": ""},
            ],
            "checkout_default_method": business_settings.get("checkout_default_method", "cash"),
            "checkout_prompt_duration_seconds": int(
                business_settings.get("checkout_prompt_duration_seconds", 6) or 6
            ),
            "waiter_call_sound": business_settings.get("waiter_call_sound", "bell1.mp3"),
            "waiter_call_cooldown_seconds": int(
                business_settings.get("waiter_call_cooldown_seconds", 10) or 10
            ),
        }

        from pronto_shared.jwt_middleware import get_current_user

        current_user = get_current_user()

        # FIX: Force localhost:9088 for local testing as config seems to be misbehaving
        base_url = config.pronto_static_public_host
        assets_path = config.static_assets_path
        restaurant_slug = config.restaurant_slug

        return {
            "app_name": config.app_name,
            "static_host_url": base_url,
            "restaurant_name": config.restaurant_name,
            "restaurant_assets": f"{base_url}{assets_path}/{restaurant_slug}",
            "current_year": datetime.now(timezone.utc).year,
            "debug_mode": config.debug_mode,
            "show_estimated_time": get_setting("show_estimated_time", True),
            "estimated_time_min": get_setting("estimated_time_min", 25),
            "estimated_time_max": get_setting("estimated_time_max", 30),
            "app_settings": app_settings,
            "employee_api_base_url": app.config.get("EMPLOYEE_API_BASE_URL"),
            "current_user": current_user,
            "customer_id": current_user.get("customer_id") if current_user else None,
            "customer_name": current_user.get("customer_name") if current_user else None,
            "session_id": current_user.get("session_id") if current_user else None,
            "table_id": current_user.get("table_id") if current_user else None,
            # Static assets URLs (short variables)
            "assets_css": f"{base_url}{assets_path}/css",
            "assets_css_shared": f"{base_url}{assets_path}/css/shared",
            "assets_css_clients": f"{base_url}{assets_path}/css/clients",
            "assets_js": f"{base_url}{assets_path}/js",
            "assets_js_shared": f"{base_url}{assets_path}/js/shared",
            "assets_js_clients": f"{base_url}{assets_path}/js/clients",
            "assets_lib": f"{base_url}{assets_path}/lib",
            "assets_images": f"{base_url}{assets_path}/pronto",
        }

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "pronto-client"}), 200

    return app


app = create_app()
