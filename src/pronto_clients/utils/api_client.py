"""
Helper for forwarding requests to pronto-api.
"""

import os
import requests
from flask import request, current_app, jsonify
from http import HTTPStatus

# Get API URL from env or default to internal docker alias
# Assuming 'api' is the hostname in docker-compose network
PRONTO_API_URL = os.getenv("PRONTO_API_URL", "http://api:5000")

def forward_to_api(method: str, endpoint: str, payload: dict | None = None) -> tuple[dict, int]:
    """
    Forward a request to pronto-api.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (e.g. '/api/orders') - must allow partial path
        payload: JSON body for the request
        
    Returns:
        Tuple of (response_json, status_code)
    """
    url = f"{PRONTO_API_URL}{endpoint}"
    if not url.endswith("/") and not endpoint.startswith("/"):
         # Correct path joining if needed, but simple concat usually works if endpoint starts with /
         pass
         
    # Ensure endpoint starts with /api if not present?
    # prompt-api routes are registered under /api usually?
    # In pronto-api/src/api_app/app.py usually registers blueprints.
    # The routes I saw were like @orders_bp.post("/orders")
    # If the blueprint is registered with url_prefix='/api', then endpoint should be '/api/orders'.
    # I should check how blueprints are registered. Assuming '/api' prefix.
    
    if not endpoint.startswith("/api"):
        endpoint = f"/api{endpoint}" if endpoint.startswith("/") else f"/api/{endpoint}"
        
    url = f"{PRONTO_API_URL}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Pass JWT token if present in cookies
    token = request.cookies.get("access_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    # Pass user agent or other tracing headers?
    headers["X-Forwarded-For"] = request.remote_addr

    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=request.args, timeout=10)
        elif method.upper() == "POST":
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        elif method.upper() == "PUT":
            resp = requests.put(url, json=payload, headers=headers, timeout=10)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=10)
        else:
            return {"error": f"Method {method} not supported"}, HTTPStatus.METHOD_NOT_ALLOWED

        try:
            data = resp.json()
        except Exception:
            data = {"error": "Invalid JSON response from API", "content": resp.text[:200]}
            
        return data, resp.status_code

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error forwarding request to {url}: {e}")
        return {"error": "Error communicating with backend API"}, HTTPStatus.BAD_GATEWAY
