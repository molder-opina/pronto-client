"""
Clients API - Modular Blueprint Structure

This package organizes clients API endpoints into logical sub-blueprints.
All endpoints are registered under the main api_bp blueprint.
"""

from flask import Blueprint

# Create main API blueprint
api_bp = Blueprint("client_api", __name__)

# Import all sub-blueprints
from pronto_clients.routes.api.auth import auth_bp
from pronto_clients.routes.api.business_info import business_info_bp
from pronto_clients.routes.api.config import config_bp
from pronto_clients.routes.api.feedback_email import feedback_email_bp
from pronto_clients.routes.api.health import health_bp
from pronto_clients.routes.api.menu import menu_bp
from pronto_clients.routes.api.notifications import notifications_bp
from pronto_clients.routes.api.orders import orders_bp
from pronto_clients.routes.api.payments import payments_bp
from pronto_clients.routes.api.sessions import sessions_bp
from pronto_clients.routes.api.shortcuts import shortcuts_bp
from pronto_clients.routes.api.split_bills import split_bills_bp
from pronto_clients.routes.api.stripe_payments import stripe_payments_bp
from pronto_clients.routes.api.support import support_bp
from pronto_clients.routes.api.waiter_calls import waiter_calls_bp
from pronto_clients.routes.api.tables import tables_bp

# Register all sub-blueprints with the main API blueprint
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(health_bp)
api_bp.register_blueprint(menu_bp)
api_bp.register_blueprint(config_bp)
api_bp.register_blueprint(waiter_calls_bp)
api_bp.register_blueprint(notifications_bp)
api_bp.register_blueprint(support_bp)
api_bp.register_blueprint(payments_bp)
api_bp.register_blueprint(split_bills_bp)
api_bp.register_blueprint(business_info_bp)
api_bp.register_blueprint(feedback_email_bp)
api_bp.register_blueprint(shortcuts_bp)
api_bp.register_blueprint(stripe_payments_bp)
api_bp.register_blueprint(orders_bp)
api_bp.register_blueprint(sessions_bp)
api_bp.register_blueprint(tables_bp)
