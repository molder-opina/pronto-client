from http import HTTPStatus

from flask import Blueprint, jsonify, request, session
from pronto_clients.routes.api.auth import customer_session_required
from pronto_clients.routes.api.orders import _forward_to_api
from pronto_clients.routes.api.table_context import (
    TableContextError,
    persist_table_context,
    resolve_table_context,
)
from sqlalchemy import func, select
from uuid import UUID
from pronto_shared.db import get_session
from pronto_shared.models import DiningSession, Table
from pronto_shared.serializers import error_response, success_response

sessions_bp = Blueprint("client_sessions_api", __name__)


def _resolve_requested_table(payload: dict) -> dict | None:
    requested_id = str(payload.get("table_id") or "").strip()
    requested_code = str(payload.get("table_number") or payload.get("table_code") or "").strip()
    lookup = requested_id or requested_code
    if not lookup:
        return None

    with get_session() as db_session:
        table = None
        if requested_id:
            try:
                requested_uuid = UUID(requested_id)
                table = (
                    db_session.execute(
                        select(Table).where(Table.id == requested_uuid, Table.is_active)
                    )
                    .scalars()
                    .one_or_none()
                )
            except ValueError:
                table = None

        if table is None and requested_code:
            table = (
                db_session.execute(
                    select(Table).where(
                        Table.is_active,
                        func.lower(Table.table_number) == func.lower(requested_code),
                    )
                )
                .scalars()
                .one_or_none()
            )

        if not table:
            return None

        return {
            "table_id": str(table.id),
            "table_code": table.table_number,
            "table_area_id": table.area_id,
            "table_area_prefix": (
                table.area.prefix if getattr(table, "area", None) is not None else None
            ),
        }

@sessions_bp.post("/sessions/open")
def open_session():
    payload = request.get_json(silent=True) or {}
    data, status, cookies = _forward_to_api("POST", "/api/sessions/open", payload)
    if status == 200:
        # Check if response has session info
        sess_data = data.get("session") or data.get("data", {}).get("session")
        if sess_data:
            session["dining_session_id"] = sess_data.get("id")
    
    resp = jsonify(data)
    resp.status_code = status
    
    if cookies:
        for cookie in cookies:
            # Forward upstream cookies (access_token is critical)
            # We enforce HttpOnly/Secure defaults if compatible, or try to copy attributes
            # Requests Cookie object: name, value, path, domain, secure, expires
            resp.set_cookie(
                key=cookie.name,
                value=cookie.value,
                path=cookie.path if cookie.path else "/",
                secure=cookie.secure,
                httponly=True if cookie.name == "access_token" else False,
                # domain=cookie.domain # Skip domain proxying to allow localhost
            )
            
    return resp

@sessions_bp.get("/sessions/me")
def get_me():
    data, status, _ = _forward_to_api("GET", "/api/sessions/me")
    return jsonify(data), status


@sessions_bp.get("/sessions/table-context")
@customer_session_required
def get_table_context():
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    try:
        context, _ = resolve_table_context(
            customer_ref, payload={}, enforce_required=False
        )
        return jsonify(success_response({"table_context": context})), HTTPStatus.OK
    except TableContextError as context_error:
        return (
            jsonify(
                error_response(
                    context_error.message,
                    {"code": context_error.code},
                )
            ),
            int(context_error.status),
        )


@sessions_bp.post("/sessions/table-context")
@customer_session_required
def set_table_context():
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return jsonify(error_response("No autenticado")), HTTPStatus.UNAUTHORIZED

    payload = request.get_json(silent=True) or {}

    # Client-side table mutation is blocked when there is an active dining session.
    # Table moves must be done through employees /sessions/<id>/move-to-table.
    requested_table = _resolve_requested_table(payload)
    dining_session_id = session.get("dining_session_id")
    if requested_table and dining_session_id:
        try:
            session_uuid = UUID(str(dining_session_id))
        except ValueError:
            session_uuid = None

        if session_uuid:
            with get_session() as db_session:
                dining_session = db_session.get(DiningSession, session_uuid)
                if (
                    dining_session
                    and dining_session.table_id
                    and dining_session.status in {"open", "active"}
                ):
                    current_table_id = str(dining_session.table_id)
                    if requested_table["table_id"] != current_table_id:
                        current_table = (
                            db_session.execute(
                                select(Table).where(
                                    Table.id == dining_session.table_id, Table.is_active
                                )
                            )
                            .scalars()
                            .one_or_none()
                        )
                        return (
                            jsonify(
                                error_response(
                                    "La mesa seleccionada no pertenece a la sesión activa",
                                    {
                                        "code": "TABLE_LOCATION_MISMATCH",
                                        "session_id": str(dining_session.id),
                                        "current_table_id": current_table_id,
                                        "current_table_code": (
                                            current_table.table_number if current_table else None
                                        ),
                                        "current_table_source": "session",
                                        "table_locked": False,
                                    },
                                )
                            ),
                            HTTPStatus.CONFLICT,
                        )

    try:
        context, customer_payload = resolve_table_context(
            customer_ref, payload=payload, enforce_required=True
        )
        persisted = persist_table_context(customer_ref, customer_payload, context)
        if not persisted:
            return (
                jsonify(
                    error_response(
                        "No se pudo persistir el contexto de mesa",
                        {"code": "TABLE_CONTEXT_PERSIST_FAILED"},
                    )
                ),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return jsonify(success_response({"table_context": context})), HTTPStatus.OK
    except TableContextError as context_error:
        return (
            jsonify(
                error_response(
                    context_error.message,
                    {"code": context_error.code},
                )
            ),
            int(context_error.status),
        )
