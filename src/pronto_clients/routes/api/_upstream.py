"""
Helpers for resolving upstream API base URLs in client BFF proxies.

This module provides:
- URL resolution for pronto-api
- Unified forwarding function for all BFF proxies
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any

import requests as http_requests
from flask import Response, request, session
from flask import jsonify as flask_jsonify

from pronto_shared.trazabilidad import get_logger

logger = get_logger(__name__)

# Default timeout for upstream requests (seconds)
DEFAULT_TIMEOUT = 5


def get_pronto_api_base_url() -> str:
    """Resolve canonical BFF→API base URL for pronto-client."""
    return (
        (os.getenv("PRONTO_API_INTERNAL_BASE_URL") or "").strip()
        or (os.getenv("PRONTO_API_BASE_URL") or "").strip()
        or "http://localhost:6082"
    ).rstrip("/")


def _build_forwarding_headers() -> dict[str, str]:
    """Build headers to forward to pronto-api."""
    headers = {
        "Content-Type": "application/json",
    }
    customer_ref = str(
        request.headers.get("X-PRONTO-CUSTOMER-REF")
        or session.get("customer_ref")
        or ""
    ).strip()
    if customer_ref:
        headers["X-PRONTO-CUSTOMER-REF"] = customer_ref

    # Forward correlation ID if present
    correlation_id = request.headers.get("X-Correlation-ID")
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    csrf_token = request.headers.get("X-CSRFToken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token

    idempotency_key = request.headers.get("X-Idempotency-Key")
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    return headers


def _filter_response_headers(response: http_requests.Response) -> list[tuple[str, str]]:
    """Filter headers that should not be forwarded from upstream response."""
    excluded_headers = {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    }
    return [
        (k, v)
        for k, v in response.raw.headers.items()
        if k.lower() not in excluded_headers
    ]


def _error_response(message: str, status: int):
    """Create an error response."""
    from pronto_shared.serializers import error_response as shared_error_response
    return shared_error_response(message), status


def forward_to_api(
    method: str,
    path: str,
    data: dict | None = None,
    *,
    stream: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[Any, int] | Response:
    """
    Forward request to pronto-api.

    This is a technical proxy (BFF) as per AGENTS.md 12.4.3.
    No business logic is applied here.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., "/api/orders")
        data: Optional JSON payload for POST/PUT
        stream: If True, use streaming response (for large responses)
        timeout: Request timeout in seconds

    Returns:
        Flask response tuple or Response object

    Raises:
        No exceptions - all errors are caught and returned as error responses
    """
    api_base_url = get_pronto_api_base_url()
    url = f"{api_base_url}{path}"
    headers = _build_forwarding_headers()

    try:
        request_kwargs = {
            "headers": headers,
            "cookies": request.cookies,
            "timeout": timeout,
            "allow_redirects": False,
        }

        if stream:
            request_kwargs["stream"] = True

        if method == "GET":
            response = http_requests.get(url, **request_kwargs)
        elif method == "POST":
            response = http_requests.post(url, json=data, **request_kwargs)
        elif method == "PUT":
            response = http_requests.put(url, json=data, **request_kwargs)
        elif method == "DELETE":
            response = http_requests.delete(url, **request_kwargs)
        else:
            return _error_response("Method not supported", HTTPStatus.METHOD_NOT_ALLOWED)

        if stream:
            # Return Response with filtered headers for streaming
            return Response(
                response.content,
                status=response.status_code,
                headers=_filter_response_headers(response),
                content_type=response.headers.get("Content-Type"),
            )
        else:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type.lower():
                return flask_jsonify(response.json()), response.status_code
            return Response(
                response.content,
                status=response.status_code,
                headers=_filter_response_headers(response),
                content_type=content_type or None,
            )

    except http_requests.Timeout:
        return _error_response("Timeout conectando a API", HTTPStatus.GATEWAY_TIMEOUT)
    except http_requests.RequestException as e:
        logger.error(
            f"Error forwarding to pronto-api: {e}",
            error={"exception": str(e)},
        )
        return _error_response("Error conectando a API", HTTPStatus.BAD_GATEWAY)
