"""
Factory for the Unified API Service (REST).
Serves Client APIs under /api/client and Employee APIs under /api/employee.

Uses JWT for authentication instead of server-side sessions.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify
from flask_cors import CORS

# Import blueprints from existing apps
from clients_app.routes.api import api_bp as client_api_bp
from employees_app.routes.api import api_bp as employee_api_bp
from shared.config import load_config
from shared.db import init_db, init_engine
from shared.error_handlers import register_error_handlers
from shared.jwt_middleware import init_jwt_middleware
from shared.logging_config import configure_logging
from shared.models import Base
from shared.services.secret_service import load_env_secrets


def create_app() -> Flask:
    load_env_secrets()

    # Validate all required environment variables (fail-fast)
    from shared.config import validate_required_env_vars, read_bool
    validate_required_env_vars(skip_in_debug=False)

    app = Flask(__name__)
    config = load_config("pronto-api")

    configure_logging(config.app_name, config.log_level)

    # Database
    init_engine(config)
    init_db(Base.metadata)

    # Load seed data if configured
    # Load seed data if configured
    if read_bool("LOAD_SEED_DATA", "false"):
        app.logger.info("Initializing seed data...")
        from shared.db import get_session
        from shared.services.seed import load_seed_data

        with get_session() as session:
            try:
                load_seed_data(session)
            except Exception as e:
                app.logger.error(f"Failed to load seed data: {e}")

    # Basic Config
    app.config["SECRET_KEY"] = config.secret_key
    app.config["APP_NAME"] = "Pronto API"
    app.config["DEBUG_MODE"] = config.debug_mode
    app.config["DEBUG"] = config.flask_debug

    # Initialize JWT middleware
    init_jwt_middleware(app)

    # Register Blueprints with prefixes
    # Client API -> /api/client
    app.register_blueprint(client_api_bp, url_prefix="/api/client")

    # Employee API -> /api/employee
    app.register_blueprint(employee_api_bp, url_prefix="/api/employee")

    # Error Handlers
    register_error_handlers(app)

    # CORS
    allowed_origins = [
        "http://localhost:6080",
        "http://localhost:6081",
        "http://127.0.0.1:6080",
        "http://127.0.0.1:6081",
    ]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins, "supports_credentials": True}})

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "pronto-api"}), 200

    return app


app = create_app()
