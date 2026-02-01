"""
Images API - Gestión de imágenes y recursos visuales

Este módulo maneja la carga, importación y generación de imágenes
usando servicios locales y de inteligencia artificial.
"""

from http import HTTPStatus

import requests
from flask import Blueprint, current_app, jsonify, request

from employees_app.decorators import admin_required
from shared.jwt_middleware import jwt_required
from shared.logging_config import get_logger
from shared.serializers import error_response, success_response
from shared.services.ai_image_service import AIImageService
from shared.services.image_service import ImageService

images_bp = Blueprint("images", __name__)
logger = get_logger(__name__)


@images_bp.post("/images/upload")
@jwt_required
def upload_product_image():
    """
    Sube un archivo local al contenedor de contenido estático.

    Form data:
    - file: Archivo de imagen a subir
    - category: Categoría de la imagen (default: 'menu')
    """
    file = request.files.get("file")
    if not file:
        return jsonify(error_response("Selecciona un archivo")), HTTPStatus.BAD_REQUEST

    category = request.form.get("category", "menu")
    try:
        meta = ImageService.save_uploaded_image(
            file,
            category=category,
            restaurant_slug=current_app.config.get("RESTAURANT_SLUG"),
        )
        return jsonify(success_response(meta)), HTTPStatus.CREATED
    except ValueError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        logger.error(f"Error uploading image: {exc}")
        return jsonify(
            error_response("No se pudo guardar la imagen")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@images_bp.post("/images/import")
@jwt_required
def import_product_image():
    """
    Descarga una imagen desde una URL externa y la almacena localmente.

    Body: {
        url: URL de la imagen a importar (requerido)
        category: Categoría de la imagen (default: 'menu')
        grayscale: Convertir a escala de grises (default: false)
    }
    """
    payload = request.get_json(silent=True) or {}
    source_url = (payload.get("url") or "").strip()
    if not source_url:
        return jsonify(error_response("La URL es requerida")), HTTPStatus.BAD_REQUEST

    category = payload.get("category", "menu")
    grayscale = bool(payload.get("grayscale"))
    service = AIImageService(current_app.config.get("RESTAURANT_SLUG"))

    try:
        meta = service.import_from_url(source_url, category=category, grayscale=grayscale)
        return jsonify(success_response(meta)), HTTPStatus.CREATED
    except requests.RequestException as exc:
        logger.error(f"Error downloading external image: {exc}")
        return jsonify(error_response("No se pudo descargar la imagen")), HTTPStatus.BAD_GATEWAY
    except Exception as exc:
        logger.error(f"Error importing image: {exc}")
        return jsonify(
            error_response("No se pudo importar la imagen")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@images_bp.post("/images/generate")
@jwt_required
def generate_product_image():
    """
    Genera una imagen usando inteligencia artificial.

    Body: {
        prompt: Descripción de la imagen a generar (requerido)
        provider: Proveedor de IA ('free' o 'openai', default: 'free')
        category: Categoría de la imagen (default: 'menu')
        grayscale: Convertir a escala de grises (default: false)
    }
    """
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    provider = (payload.get("provider") or AIImageService.FREE_PROVIDER).lower()
    category = payload.get("category", "menu")
    grayscale = bool(payload.get("grayscale"))

    service = AIImageService(current_app.config.get("RESTAURANT_SLUG"))

    try:
        meta = service.generate_image(
            prompt, provider=provider, category=category, grayscale=grayscale
        )
        return jsonify(success_response(meta)), HTTPStatus.CREATED
    except ValueError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        logger.error(f"Error generating image with provider '{provider}': {exc}")
        return jsonify(
            error_response("No se pudo generar la imagen con IA")
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@images_bp.post("/images/profiles/seed")
@admin_required
def seed_profile_avatars():
    """
    Genera un lote de avatares en escala de grises para perfiles de staff/clientes.

    Body: {
        provider: Proveedor de IA ('free' o 'openai', default: 'free')
        count: Número de avatares a generar (1-20, default: 10)
    }
    """
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or AIImageService.FREE_PROVIDER).lower()
    count = payload.get("count", 10)
    try:
        count = max(1, min(20, int(count)))
    except (TypeError, ValueError):
        count = 10

    service = AIImageService(current_app.config.get("RESTAURANT_SLUG"))

    try:
        images = service.generate_profile_set(count=count, provider=provider)
        return jsonify(
            success_response({"generated": len(images), "images": images})
        ), HTTPStatus.CREATED
    except ValueError as exc:
        return jsonify(error_response(str(exc))), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        logger.error(f"Error generating profile avatars: {exc}")
        return jsonify(
            error_response("No se pudieron generar los perfiles con IA")
        ), HTTPStatus.INTERNAL_SERVER_ERROR
