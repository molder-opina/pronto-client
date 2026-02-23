"""
Shared table context resolution for client-side order flows.

Canonical behavior:
- Table context persists in customer_session_store payload (Redis-backed)
- No table_id storage in flask.session
- Source priority on resolve: kiosk > qr > manual
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from pronto_shared.db import get_session
from pronto_shared.models import Table
from pronto_shared.services.customer_session_store import customer_session_store

ALLOWED_TABLE_SOURCES = {"kiosk", "qr", "manual", "session"}


@dataclass
class TableContextError(Exception):
    code: str
    message: str
    status: int = HTTPStatus.BAD_REQUEST


def _normalize_source(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in ALLOWED_TABLE_SOURCES:
        return normalized
    return None


def _resolve_table(identifier: Any) -> dict[str, Any] | None:
    raw = str(identifier or "").strip()
    if not raw:
        return None

    with get_session() as db_session:
        table = None

        try:
            table_uuid = UUID(raw)
            table = (
                db_session.execute(
                    select(Table).where(Table.id == table_uuid, Table.is_active)
                )
                .scalars()
                .one_or_none()
            )
        except ValueError:
            table = None

        if table is None:
            table = (
                db_session.execute(
                    select(Table).where(
                        Table.is_active,
                        func.lower(Table.table_number) == func.lower(raw),
                    )
                )
                .scalars()
                .one_or_none()
            )

        if table is None:
            return None

        return {
            "id": str(table.id),
            "code": table.table_number,
            "area_id": table.area_id,
            "area_prefix": getattr(table.area, "prefix", None) if getattr(table, "area", None) else None,
        }


def _load_customer_payload(customer_ref: str) -> dict[str, Any]:
    customer_payload = customer_session_store.get_customer(customer_ref)
    if not customer_payload:
        raise TableContextError(
            code="CUSTOMER_SESSION_REQUIRED",
            message="Sesion de cliente no valida",
            status=HTTPStatus.UNAUTHORIZED,
        )
    return dict(customer_payload)


def resolve_table_context(
    customer_ref: str,
    payload: dict[str, Any] | None,
    *,
    enforce_required: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Resolve table context for the current customer session.

    Returns:
      (resolved_context, current_customer_payload)
    """
    payload = payload or {}
    current = _load_customer_payload(customer_ref)

    kind = str(current.get("kind") or "").strip().lower()
    current_source = _normalize_source(current.get("table_source"))
    current_table_id = current.get("table_id")
    current_table_code = current.get("table_code")

    requested_source = _normalize_source(payload.get("table_source"))
    requested_id = payload.get("table_id")
    requested_code = payload.get("table_number") or payload.get("table_code")
    has_explicit_change = bool(
        str(requested_id or "").strip() or str(requested_code or "").strip()
    )

    # Priority 1: kiosk fixed table
    if kind == "kiosk":
        kiosk_ref = current.get("kiosk_location")
        kiosk_table = _resolve_table(kiosk_ref)
        if not kiosk_table:
            raise TableContextError(
                code="KIOSK_TABLE_NOT_CONFIGURED",
                message="Kiosko sin mesa configurada",
                status=HTTPStatus.CONFLICT,
            )
        return (
            {
                "table_id": kiosk_table["id"],
                "table_code": kiosk_table["code"],
                "table_source": "kiosk",
                "table_locked": True,
                "table_area_id": kiosk_table.get("area_id"),
                "table_area_prefix": kiosk_table.get("area_prefix"),
            },
            current,
        )

    # Priority 2: QR lock
    if current_source == "qr":
        qr_table = _resolve_table(current_table_id or current_table_code)
        if not qr_table:
            if enforce_required:
                raise TableContextError(
                    code="TABLE_REQUIRED",
                    message="Selecciona una mesa para generar la orden",
                    status=HTTPStatus.BAD_REQUEST,
                )
            return (
                {
                    "table_id": None,
                    "table_code": None,
                    "table_source": "qr",
                    "table_locked": True,
                    "table_area_id": None,
                    "table_area_prefix": None,
                },
                current,
            )

        if has_explicit_change:
            requested = _resolve_table(requested_id or requested_code)
            if not requested or requested["id"] != qr_table["id"]:
                raise TableContextError(
                    code="TABLE_LOCKED_BY_QR",
                    message="La mesa de QR no puede modificarse manualmente",
                    status=HTTPStatus.CONFLICT,
                )

        return (
            {
                "table_id": qr_table["id"],
                "table_code": qr_table["code"],
                "table_source": "qr",
                "table_locked": True,
                "table_area_id": qr_table.get("area_id"),
                "table_area_prefix": qr_table.get("area_prefix"),
            },
            current,
        )

    # Priority 3: explicit manual/qr payload
    if has_explicit_change:
        requested = _resolve_table(requested_id or requested_code)
        if not requested:
            raise TableContextError(
                code="TABLE_REQUIRED",
                message="Selecciona una mesa para generar la orden",
                status=HTTPStatus.BAD_REQUEST,
            )

        source = requested_source or current_source or "manual"
        if source not in ALLOWED_TABLE_SOURCES:
            source = "manual"

        return (
            {
                "table_id": requested["id"],
                "table_code": requested["code"],
                "table_source": source,
                "table_locked": source in {"kiosk", "qr"},
                "table_area_id": requested.get("area_id"),
                "table_area_prefix": requested.get("area_prefix"),
            },
            current,
        )

    # Priority 4: existing persisted context
    persisted = _resolve_table(current_table_id or current_table_code)
    if persisted:
        source = current_source or "manual"
        return (
            {
                "table_id": persisted["id"],
                "table_code": persisted["code"],
                "table_source": source,
                "table_locked": source in {"kiosk", "qr"},
                "table_area_id": persisted.get("area_id"),
                "table_area_prefix": persisted.get("area_prefix"),
            },
            current,
        )

    if enforce_required:
        raise TableContextError(
            code="TABLE_REQUIRED",
            message="Selecciona una mesa para generar la orden",
            status=HTTPStatus.BAD_REQUEST,
        )

    return (
        {
            "table_id": None,
            "table_code": None,
            "table_source": None,
            "table_locked": False,
            "table_area_id": None,
            "table_area_prefix": None,
        },
        current,
    )


def persist_table_context(
    customer_ref: str,
    current_payload: dict[str, Any],
    resolved_context: dict[str, Any],
) -> bool:
    updated = dict(current_payload)
    previous_table_id = current_payload.get("table_id")
    next_table_id = resolved_context.get("table_id")
    updated["table_id"] = next_table_id
    updated["table_code"] = resolved_context.get("table_code")
    updated["table_source"] = resolved_context.get("table_source")
    updated["table_locked"] = bool(resolved_context.get("table_locked"))
    updated["table_area_id"] = resolved_context.get("table_area_id")
    updated["table_area_prefix"] = resolved_context.get("table_area_prefix")
    if next_table_id and str(previous_table_id or "") != str(next_table_id):
        current_version = int(current_payload.get("table_version") or 0)
        updated["table_version"] = current_version + 1
    else:
        updated["table_version"] = int(current_payload.get("table_version") or 1)
    return customer_session_store.update_session(customer_ref, updated)
