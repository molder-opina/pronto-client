"""
Centralized error handlers for Flask applications.
"""

from http import HTTPStatus

from flask import Flask, jsonify
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from shared.logging_config import get_logger
from shared.serializers import error_response
from shared.validation import ValidationError

logger = get_logger(__name__)


def register_error_handlers(app: Flask) -> None:
    """
    Register centralized error handlers for the Flask app.

    Args:
        app: Flask application instance
    """

    from flask import render_template, request

    def should_return_json():
        """
        Determine if the response should be JSON based on request context.
        Returns true if path starts with /api/ or client explicitly asks for JSON (and not HTML).
        """
        return request.path.startswith("/api/") or (
            request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html
        )

    @app.errorhandler(ValidationError)
    def handle_validation_error(e: ValidationError):
        """Handle custom validation errors."""
        logger.warning(f"Validation error: {e}")
        if should_return_json():
            return jsonify(error_response(str(e))), HTTPStatus.BAD_REQUEST
        return render_template("error.html", error=e, code=400), 400

    @app.errorhandler(PydanticValidationError)
    def handle_pydantic_validation_error(e: PydanticValidationError):
        """Handle Pydantic validation errors."""
        logger.warning(f"Pydantic validation error: {e}")
        if should_return_json():
            return jsonify(
                error_response("Datos inválidos", {"details": e.errors()})
            ), HTTPStatus.BAD_REQUEST
        return render_template("error.html", error="Datos inválidos", code=400), 400

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(e: SQLAlchemyError):
        """Handle database errors."""
        logger.error(f"Database error: {e}", exc_info=True)
        if should_return_json():
            return jsonify(
                error_response("Error de base de datos")
            ), HTTPStatus.INTERNAL_SERVER_ERROR
        return render_template("error.html", error="Error de base de datos", code=500), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """Handle HTTP exceptions from Werkzeug."""
        logger.warning(f"HTTP exception {e.code}: {e.description}")
        if should_return_json():
            return jsonify(error_response(e.description or str(e))), e.code
        return render_template("error.html", error=e.description, code=e.code), e.code

    @app.errorhandler(Exception)
    def handle_generic_exception(e: Exception):
        """Handle any unhandled exceptions."""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        if should_return_json():
            return jsonify(
                error_response("Error interno del servidor")
            ), HTTPStatus.INTERNAL_SERVER_ERROR
        return render_template("error.html", error="Error interno del servidor", code=500), 500

    @app.errorhandler(404)
    def handle_not_found(e):
        """Handle 404 errors."""
        if should_return_json():
            return jsonify(error_response("Recurso no encontrado")), HTTPStatus.NOT_FOUND
        return render_template("error.html", error="Recurso no encontrado", code=404), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        """Handle 405 errors."""
        if should_return_json():
            return jsonify(error_response("Método no permitido")), HTTPStatus.METHOD_NOT_ALLOWED
        return render_template("error.html", error="Método no permitido", code=405), 405

    @app.errorhandler(500)
    def handle_internal_server_error(e):
        """Handle 500 errors."""
        logger.error(f"Internal server error: {e}", exc_info=True)
        if should_return_json():
            return jsonify(
                error_response("Error interno del servidor")
            ), HTTPStatus.INTERNAL_SERVER_ERROR
        return render_template("error.html", error="Error interno del servidor", code=500), 500
