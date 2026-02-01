"""
Scoped API Registration Helper

Architecture:
    - Perímetro: /waiter/api/*, /chef/api/*, /cashier/api/*, /admin/api/*
    - Núcleo: routes/api/* (shared handlers)
    - Validación: apply_api_scope_guard validates URL scope == session.active_scope

This module provides a helper to register the shared API blueprint
multiple times with different URL prefixes (one per scope).
"""


def register_scoped_apis(app, shared_api_blueprint):
    """
    Register the shared API blueprint multiple times with scope-specific prefixes.

    This creates:
        /api/*        → legacy (no scope validation)
        /waiter/api/* → validates session.active_scope == "waiter"
        /chef/api/*   → validates session.active_scope == "chef"
        /cashier/api/* → validates session.active_scope == "cashier"
        /admin/api/*  → validates session.active_scope == "admin"
        /system/api/* → validates session.active_scope == "system"

    Usage (in app.py):
        from routes.api_scoped import register_scoped_apis
        from routes.api import api_bp

        # Register legacy /api/* routes
        app.register_blueprint(api_bp)

        # Register scoped /<scope>/api/* routes
        register_scoped_apis(app, api_bp)

        # Apply scope validation middleware
        from shared.scope_guard import apply_api_scope_guard
        apply_api_scope_guard(app)
    """
    scopes = ["waiter", "chef", "cashier", "admin", "system"]

    for scope in scopes:
        # Register the same blueprint with a different URL prefix
        # Flask allows the same blueprint to be registered multiple times
        # with different names and URL prefixes
        app.register_blueprint(
            shared_api_blueprint,
            name=f"{scope}_api",  # Unique name per registration
            url_prefix=f"/{scope}/api",  # Scope-specific prefix
        )
