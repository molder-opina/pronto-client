"""
Employees API - Modular Blueprint Structure

This package organizes the employees API endpoints into logical sub-blueprints.
Each module handles a specific resource or domain.
"""

import logging
from flask import Blueprint

logger = logging.getLogger(__name__)

# Create main API blueprint
api_bp = Blueprint("api", __name__)

# Import and register sub-blueprints
from .admin_config import admin_config_bp
from .analytics import analytics_bp
from .areas import areas_bp
from .auth import auth_bp
from .branding import branding_bp
from .business_info import business_info_bp
from .config import config_bp
from .customers import customers_bp
from .day_periods import day_periods_bp
from .debug import debug_bp
from .discount_codes import discount_codes_bp
from .employees import employees_bp
from .feedback import feedback_bp
from .images import images_bp
from .menu import menu_bp
from .modifiers import modifiers_bp
from .notifications import notifications_bp
from .orders import orders_bp
from .promotions import promotions_bp
from .realtime import realtime_bp
from .reports import reports_bp
from .roles import roles_bp
from .sessions import sessions_bp
from .settings import settings_bp
from .table_assignments import table_assignments_bp
from .tables import tables_bp
from .waiter_calls import waiter_calls_bp

# Register sub-blueprints
api_bp.register_blueprint(orders_bp)
api_bp.register_blueprint(sessions_bp)
api_bp.register_blueprint(menu_bp)
api_bp.register_blueprint(employees_bp)
api_bp.register_blueprint(config_bp)
api_bp.register_blueprint(admin_config_bp)
api_bp.register_blueprint(waiter_calls_bp)
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(customers_bp)
api_bp.register_blueprint(tables_bp)
api_bp.register_blueprint(reports_bp)
api_bp.register_blueprint(modifiers_bp)
api_bp.register_blueprint(images_bp)
api_bp.register_blueprint(areas_bp)
api_bp.register_blueprint(promotions_bp)
api_bp.register_blueprint(discount_codes_bp)
api_bp.register_blueprint(debug_bp)
api_bp.register_blueprint(business_info_bp)
api_bp.register_blueprint(settings_bp)
api_bp.register_blueprint(roles_bp)
api_bp.register_blueprint(feedback_bp)
api_bp.register_blueprint(day_periods_bp)
api_bp.register_blueprint(realtime_bp)
api_bp.register_blueprint(branding_bp)
api_bp.register_blueprint(table_assignments_bp)
api_bp.register_blueprint(notifications_bp)
api_bp.register_blueprint(analytics_bp)


# Health check endpoint
@api_bp.get("/health")
def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "service": "employees-api"}, 200


__all__ = ["api_bp"]
