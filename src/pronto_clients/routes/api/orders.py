"""
Client BFF - Orders Blueprint.
Wraps calls to pronto-api. Stateless, does not use flask.session.
"""

import logging
import requests
from http import HTTPStatus
from flask import Blueprint, current_app, jsonify, request

from pronto_shared.services.dining_session_service import store_customer_ref
from pronto_shared.jwt_middleware import jwt_required
from pronto_shared.serializers import error_response, success_response

orders_bp = Blueprint("client_orders_api", __name__)

logger = logging.getLogger(__name__)

@orders_bp.post("/orders")
@jwt_required
def create_order():
    """
    Proxy to pronto-api for creating an order.
    Stateless: does not store session info in flask.session.
    """
    payload = request.get_json(silent=True) or {}
    api_base_url = current_app.config.get("API_BASE_URL", "http://localhost:6082")
    
    # Extract auth header to forward to pronto-api
    auth_header = request.headers.get("Authorization")
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        # 1. Forward request to pronto-api
        resp = requests.post(
            f"{api_base_url}/api/orders",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code != HTTPStatus.CREATED:
            return jsonify(resp.json()), resp.status_code
        
        data = resp.json()
        
        # 2. Handle PII -> Redis ref (optional, for tracking without session)
        customer_data = payload.get("customer")
        if customer_data:
            ref = store_customer_ref(customer_data)
            logger.info(f"Stored customer PII reference {ref} in Redis")

        return jsonify(data), HTTPStatus.CREATED

    except requests.exceptions.RequestException as e:
        logger.error(f"Error proxying order to pronto-api: {e}")
        return jsonify(error_response("Error de comunicación con el servicio central")), HTTPStatus.SERVICE_UNAVAILABLE
    except Exception as e:
        logger.error(f"Unexpected error in client create_order: {e}", exc_info=True)
        return jsonify(error_response("Error interno al procesar la orden")), HTTPStatus.INTERNAL_SERVER_ERROR


@orders_bp.get("/orders/current")
@jwt_required
def get_current_session_orders():
    """
    Get all orders for a session. session_id must be provided as a query param.
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify(error_response("session_id query parameter is required")), HTTPStatus.BAD_REQUEST

    api_base_url = current_app.config.get("API_BASE_URL", "http://localhost:6082")
    auth_header = request.headers.get("Authorization")
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        # Call pronto-api to get orders filtered by session_id
        resp = requests.get(
            f"{api_base_url}/api/orders?session_id={session_id}",
            headers=headers,
            timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Error fetching orders from api: {e}")
        return jsonify(error_response("Error al obtener historial")), HTTPStatus.INTERNAL_SERVER_ERROR
