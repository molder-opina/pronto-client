"""
API endpoints para gestión de branding del restaurante.
Permite subir/generar logos, iconos, banners y configurar colores.
"""

import base64
import binascii
import imghdr
import os
import subprocess  # nosec B404: se usa para ejecutar scripts internos controlados
import urllib.parse
from http import HTTPStatus

import requests
from flask import Blueprint, current_app, jsonify, request

from employees_app.decorators import role_required

branding_bp = Blueprint("branding", __name__, url_prefix="/branding")

DEFAULT_STATIC_ASSETS_PATH = "/assets"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"png"}


def _decode_base64_image(data: str) -> bytes:
    """Decode and validate a base64-encoded image payload."""
    decoded = base64.b64decode(data, validate=True)
    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen excede el tamaño máximo permitido")
    image_type = imghdr.what(None, decoded)
    if image_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Formato de imagen no permitido")
    return decoded


def _download_image(url: str, output_path: str) -> None:
    """Download an image from a trusted URL and persist it to disk."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        raise ValueError("Respuesta no es una imagen")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen descargada excede el tamaño máximo permitido")
    with open(output_path, "wb") as output_file:
        output_file.write(response.content)
    os.chmod(output_path, 0o644)


def get_restaurant_slug():
    """Get restaurant slug from app config (derived from RESTAURANT_NAME)."""
    from shared.config import load_config

    config = load_config("employee")
    return config.restaurant_slug


def get_static_url():
    """Get static base URL from app config."""
    return current_app.config.get("PRONTO_STATIC_CONTAINER_HOST", "http://localhost:9088")


def get_pronto_static_container_host():
    """Get PRONTO_STATIC_CONTAINER_HOST from app config."""
    return current_app.config.get("PRONTO_STATIC_CONTAINER_HOST", "http://localhost:9088")


def get_static_assets_path():
    """Get STATIC_ASSETS_PATH from app config."""
    return current_app.config.get("STATIC_ASSETS_PATH", "/assets")


def get_restaurant_name():
    """Get restaurant name from app config."""
    return current_app.config.get("RESTAURANT_NAME", "Restaurante")


def get_assets_root():
    """Get filesystem root for static assets."""
    root = current_app.config.get("STATIC_ASSETS_ROOT") or os.getenv("STATIC_ASSETS_ROOT")
    if not root:
        fallback = os.getenv("STATIC_ASSETS_PATH")
        if fallback and os.path.isabs(fallback):
            root = fallback
    return root or "/var/www/pronto-static/assets"


def get_assets_css():
    """Get CSS assets base URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/css"


def get_assets_css_employees():
    """Get employees CSS assets URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/css/employees"


def get_assets_css_clients():
    """Get clients CSS assets URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/css/clients"


def get_assets_js():
    """Get JS assets base URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/js"


def get_assets_js_employees():
    """Get employees JS assets URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/js/employees"


def get_assets_js_clients():
    """Get clients JS assets URL."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    return f"{base_url}{assets_path}/js/clients"


def get_static_url_for_path(path_type: str) -> str:
    """Build static URL based on path type using config variables."""
    base_url = get_pronto_static_container_host()
    assets_path = get_static_assets_path()
    slug = get_restaurant_slug()
    return f"{base_url}{assets_path}/{slug}/{path_type}"


def get_paths():
    """Get dynamic paths based on restaurant slug."""
    slug = get_restaurant_slug()
    base_root = get_assets_root()
    return {
        "branding": f"{base_root}/{slug}/branding",
        "icons": f"{base_root}/{slug}/icons",
        "products": f"{base_root}/{slug}/products",
    }


def ensure_directories(raise_on_error: bool = True) -> bool:
    """Asegura que existan los directorios necesarios."""
    paths = get_paths()
    try:
        for path in paths.values():
            os.makedirs(path, exist_ok=True)
    except OSError as exc:
        current_app.logger.error("Branding assets path error: %s", exc)
        if raise_on_error:
            raise
        return False
    return True


@branding_bp.route("/config", methods=["GET"])
@role_required(["system", "admin"])
def get_branding_config():
    """Obtiene la configuración actual de branding."""
    ensure_directories(raise_on_error=False)
    paths = get_paths()
    slug = get_restaurant_slug()
    static_url = get_static_url()

    # Verificar qué archivos existen
    files = {
        "logo": os.path.exists(f"{paths['branding']}/logo.png"),
        "icon": os.path.exists(f"{paths['branding']}/icon.png"),
        "banner": os.path.exists(f"{paths['branding']}/banner.png"),
        "placeholder": os.path.exists(f"{paths['icons']}/placeholder.png"),
    }

    # Contar imágenes de productos
    product_images = 0
    if os.path.exists(paths["products"]):
        product_images = len([f for f in os.listdir(paths["products"]) if f.endswith(".png")])

    return jsonify(
        {
            "success": True,
            "data": {
                "restaurant_name": get_restaurant_name(),
                "restaurant_slug": slug,
                "static_url": static_url,
                "branding_url": f"{static_url}/assets/{slug}/branding",
                "files": files,
                "product_images_count": product_images,
                "available_apis": ["pollinations", "stability", "replicate"],
                "paths": paths,
            },
        }
    )


@branding_bp.route("/upload/<asset_type>", methods=["POST"])
@role_required(["system", "admin"])
def upload_branding_asset(asset_type):
    """
    Sube un archivo de branding.
    asset_type: logo, icon, banner, placeholder
    """
    try:
        ensure_directories()
    except OSError as exc:
        return jsonify(
            {"success": False, "error": f"No se pudo preparar el directorio de branding: {exc}"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
    paths = get_paths()
    slug = get_restaurant_slug()
    static_url = get_static_url()

    valid_types = {
        "logo": (paths["branding"], "logo.png"),
        "icon": (paths["branding"], "icon.png"),
        "banner": (paths["branding"], "banner.png"),
        "placeholder": (paths["icons"], "placeholder.png"),
    }

    if asset_type not in valid_types:
        return jsonify(
            {
                "success": False,
                "error": f"Tipo de asset inválido. Válidos: {list(valid_types.keys())}",
            }
        ), HTTPStatus.BAD_REQUEST

    # Verificar si es upload de archivo o base64
    if "file" in request.files:
        file = request.files["file"]
        if file.filename == "":
            return jsonify(
                {"success": False, "error": "No se seleccionó archivo"}
            ), HTTPStatus.BAD_REQUEST

        path, filename = valid_types[asset_type]
        filepath = f"{path}/{filename}"
        file.save(filepath)
        os.chmod(filepath, 0o644)

    elif request.is_json and "base64" in request.json:
        # Decodificar base64
        try:
            data = request.json["base64"]
            # Remover prefijo data:image/png;base64, si existe
            if "," in data:
                data = data.split(",")[1]
            image_data = _decode_base64_image(data)

            path, filename = valid_types[asset_type]
            filepath = f"{path}/{filename}"

            with open(filepath, "wb") as f:
                f.write(image_data)
            os.chmod(filepath, 0o644)

        except (ValueError, binascii.Error) as e:
            return jsonify(
                {"success": False, "error": f"Error decodificando base64: {e!s}"}
            ), HTTPStatus.BAD_REQUEST
    else:
        return jsonify(
            {"success": False, "error": "Envía 'file' o 'base64'"}
        ), HTTPStatus.BAD_REQUEST

    path, filename = valid_types[asset_type]
    return jsonify(
        {
            "success": True,
            "message": f"{asset_type} actualizado correctamente",
            "url": f"{static_url}/assets/{slug}/{path.split('/')[-1]}/{filename}",
        }
    )


@branding_bp.route("/generate/<asset_type>", methods=["POST"])
@role_required(["system", "admin"])
def generate_branding_asset(asset_type):
    """
    Genera un asset de branding usando IA.
    asset_type: logo, icon, banner, placeholder, all
    """
    try:
        ensure_directories()
    except OSError as exc:
        return jsonify(
            {"success": False, "error": f"No se pudo preparar el directorio de branding: {exc}"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
    paths = get_paths()
    slug = get_restaurant_slug()
    static_url = get_static_url()
    restaurant_name = get_restaurant_name()

    data = request.get_json() or {}
    data.get("api", "pollinations")
    style = data.get("style", "modern")
    custom_prompt = data.get("prompt", "")

    valid_types = ["logo", "icon", "banner", "placeholder", "all"]
    if asset_type not in valid_types:
        return jsonify(
            {"success": False, "error": f"Tipo inválido. Válidos: {valid_types}"}
        ), HTTPStatus.BAD_REQUEST

    # Definir prompts
    prompts = {
        "logo": f"Restaurant logo for '{restaurant_name}', {style} design, professional branding, white background, centered",
        "icon": f"Simple app icon for '{restaurant_name}' restaurant, {style}, single symbol, centered",
        "banner": f"Wide banner for '{restaurant_name}' restaurant, {style}, elegant food presentation, warm lighting",
        "placeholder": f"Food placeholder image, elegant plate, {style}, professional photography, soft lighting",
    }

    if custom_prompt:
        prompts[asset_type] = custom_prompt

    # Configurar dimensiones
    dimensions = {
        "logo": (512, 512),
        "icon": (128, 128),
        "banner": (1200, 400),
        "placeholder": (256, 256),
    }

    results = []
    types_to_generate = (
        [asset_type] if asset_type != "all" else ["logo", "icon", "banner", "placeholder"]
    )

    for atype in types_to_generate:
        prompt = prompts.get(atype, prompts["placeholder"])
        width, height = dimensions.get(atype, (512, 512))

        # Determinar path de salida
        if atype in ["logo", "icon", "banner"]:
            output_path = f"{paths['branding']}/{atype}.png"
        else:
            output_path = f"{paths['icons']}/{atype}.png"

        # Generar con Pollinations (gratis)
        try:
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
            parsed_url = urllib.parse.urlparse(url)
            if parsed_url.scheme not in ("http", "https"):
                raise ValueError("Scheme no permitido en la URL solicitada")

            _download_image(url, output_path)

            results.append({"type": atype, "success": True, "path": output_path})
        except Exception as e:
            results.append({"type": atype, "success": False, "error": str(e)})

    return jsonify(
        {
            "success": all(r["success"] for r in results),
            "results": results,
            "branding_url": f"{static_url}/assets/{slug}/branding",
        }
    )


@branding_bp.route("/generate-products", methods=["POST"])
@role_required(["system", "admin"])
def generate_product_images():
    """
    Inicia la generación de imágenes de productos en background.
    """
    data = request.get_json() or {}
    category = data.get("category", "")
    limit = data.get("limit", 10)
    api = data.get("api", "pollinations")
    allowed_apis = {"pollinations", "stability", "replicate"}
    if api not in allowed_apis:
        return jsonify(
            {"success": False, "error": f"API no soportada. Válidas: {sorted(allowed_apis)}"}
        ), HTTPStatus.BAD_REQUEST

    # Construir comando
    cmd = ["bash", "/apps/pronto/pronto-app/bin/generate-product-images.sh"]
    cmd.extend(["-a", api])
    cmd.extend(["-l", str(limit)])

    if category:
        cmd.extend(["-c", category])

    # Ejecutar en background
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # nosec B603: comando fijo con argumentos validados
        )

        return jsonify(
            {
                "success": True,
                "message": f"Generación iniciada en background (PID: {process.pid})",
                "params": {"category": category or "Todas", "limit": limit, "api": api},
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@branding_bp.route("/products", methods=["GET"])
@role_required(["system", "admin"])
def list_product_images():
    """Lista las imágenes de productos generadas."""
    ensure_directories(raise_on_error=False)
    paths = get_paths()
    slug = get_restaurant_slug()
    static_url = get_static_url()

    images = []
    if os.path.exists(paths["products"]):
        for filename in os.listdir(paths["products"]):
            if filename.endswith(".png"):
                filepath = f"{paths['products']}/{filename}"
                stat = os.stat(filepath)
                images.append(
                    {"filename": filename, "size": stat.st_size, "modified": stat.st_mtime}
                )

    images.sort(key=lambda x: x["modified"], reverse=True)

    return jsonify(
        {
            "success": True,
            "count": len(images),
            "base_url": f"{static_url}/assets/{slug}/products",
            "images": images,
        }
    )


@branding_bp.route("/delete/<asset_type>", methods=["DELETE"])
@role_required(["system"])
def delete_branding_asset(asset_type):
    """Elimina un asset de branding."""
    paths = get_paths()

    valid_types = {
        "logo": f"{paths['branding']}/logo.png",
        "icon": f"{paths['branding']}/icon.png",
        "banner": f"{paths['branding']}/banner.png",
        "placeholder": f"{paths['icons']}/placeholder.png",
    }

    if asset_type not in valid_types:
        return jsonify(
            {"success": False, "error": f"Tipo inválido. Válidos: {list(valid_types.keys())}"}
        ), HTTPStatus.BAD_REQUEST

    filepath = valid_types[asset_type]

    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({"success": True, "message": f"{asset_type} eliminado"})
    else:
        return jsonify({"success": False, "error": "Archivo no existe"}), HTTPStatus.NOT_FOUND
