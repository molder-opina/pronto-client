"""
Client API routes package.

This package contains all client-facing API routes for pronto-client.
Most routes are BFF proxies to pronto-api:6082 (business logic).
Some routes are BFF cache (read from pronto-api and cached locally).
Some routes are UI-only (static metadata without business logic).

Reference: AGENTS.md section 12.4.2, 12.4.3
"""

from flask import Blueprint

from .auth import auth_bp
from .config import config_bp
from .support import support_bp
from .shortcuts import shortcuts_bp
from .business_info import business_info_bp
from .menu import menu_bp
from .tables import tables_bp
from .payments import payments_bp

from .split_bills import split_bills_bp
from .waiter_calls import waiter_calls_bp
from .stripe_payments import stripe_payments_bp
from .notifications import notifications_bp
from .orders import orders_bp
from .sessions import sessions_bp
from .feedback_email import feedback_email_bp

api_bp = Blueprint("api", __name__)

api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(config_bp)
api_bp.register_blueprint(support_bp)
api_bp.register_blueprint(shortcuts_bp)
api_bp.register_blueprint(business_info_bp)
api_bp.register_blueprint(menu_bp)
api_bp.register_blueprint(tables_bp)
api_bp.register_blueprint(payments_bp)
api_bp.register_blueprint(split_bills_bp)
api_bp.register_blueprint(waiter_calls_bp)
api_bp.register_blueprint(stripe_payments_bp)
api_bp.register_blueprint(notifications_bp)
api_bp.register_blueprint(orders_bp)
api_bp.register_blueprint(sessions_bp)
api_bp.register_blueprint(feedback_email_bp)
