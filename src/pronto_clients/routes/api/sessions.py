"""
Sessions endpoints for clients API.
"""

import logging
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from flask import Blueprint, jsonify, make_response, request
from sqlalchemy.exc import IntegrityError

from pronto_shared.config import SESSION_TTL_HOURS
from pronto_shared.db import get_session
from pronto_shared.models import Customer, DiningSession, Table
from pronto_shared.services.customer_service import (
    create_anonymous_customer,
    get_customer_by_anon_id,
)

logger = logging.getLogger(__name__)

sessions_bp = Blueprint("client_sessions", __name__)


@sessions_bp.post("/sessions/open")
def open_session():
    """Open a new dining session for a table or reuse existing open session."""
    data = request.get_json(silent=True) or {}
    table_id = data.get("table_id")
    anon_id = data.get("anon_id")

    if not table_id:
        return jsonify({"error": "table_id requerido"}), HTTPStatus.BAD_REQUEST

    with get_session() as db:
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            return jsonify({"error": "Mesa no encontrada"}), HTTPStatus.NOT_FOUND

        existing = (
            db.query(DiningSession)
            .filter(DiningSession.table_id == table_id, DiningSession.status == "open")
            .first()
        )

        if existing:
            if existing.is_expired:
                existing.status = "closed"
                db.commit()
            else:
                cust = (
                    db.query(Customer)
                    .filter(Customer.id == existing.customer_id)
                    .first()
                )
                from pronto_shared.jwt_service import create_client_token

                access_token = create_client_token(
                    customer_id=cust.id,
                    customer_name=cust.name,
                    customer_phone=cust.phone,
                    table_id=existing.table_id,
                    session_id=existing.id,
                )

                response_data = {
                    "success": True,
                    "access_token": access_token,
                    "data": {
                        "session_id": existing.id,
                        "table_id": existing.table_id,
                        "anon_id": cust.anon_id if cust else None,
                        "status": existing.status,
                        "expires_at": existing.expires_at.isoformat()
                        if existing.expires_at
                        else None,
                    },
                }

                response = make_response(jsonify(response_data), HTTPStatus.OK)

                # Set JWT cookie
                response.set_cookie(
                    "access_token",
                    access_token,
                    httponly=True,
                    secure=request.is_secure,
                    samesite="Lax",
                    max_age=86400,  # 24 hours
                    path="/",
                )

                return response

        if anon_id:
            cust = get_customer_by_anon_id(db, anon_id) or create_anonymous_customer(db)
        else:
            cust = create_anonymous_customer(db)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)

        new_sess = DiningSession(
            table_id=table_id,
            customer_id=cust.id,
            status="open",
            expires_at=expires_at,
            opened_at=datetime.now(timezone.utc),
        )

        try:
            db.add(new_sess)
            db.commit()
            db.refresh(new_sess)
        except IntegrityError:
            # Race condition: another request created the session concurrently
            db.rollback()
            logger.warning(
                f"Race condition detected for table {table_id}, re-querying existing session"
            )

            # Re-query the existing session created by the concurrent request
            existing = (
                db.query(DiningSession)
                .filter(
                    DiningSession.table_id == table_id, DiningSession.status == "open"
                )
                .first()
            )

            if existing:
                if existing.is_expired:
                    existing.status = "closed"
                    db.commit()
                    logger.info(
                        f"Recovered expired session {existing.id} for table {table_id}, closing it"
                    )
                else:
                    cust = (
                        db.query(Customer)
                        .filter(Customer.id == existing.customer_id)
                        .first()
                    )
                    logger.info(
                        f"Recovered session {existing.id} for table {table_id} after IntegrityError"
                    )
                    return jsonify(
                        {
                            "success": True,
                            "data": {
                                "session_id": existing.id,
                                "table_id": existing.table_id,
                                "anon_id": cust.anon_id if cust else None,
                                "status": existing.status,
                                "expires_at": existing.expires_at.isoformat()
                                if existing.expires_at
                                else None,
                            },
                        }
                    ), HTTPStatus.OK

            # Should not happen, but handle gracefully
            return jsonify(
                {"error": "Unable to create or recover session for table"}
            ), HTTPStatus.INTERNAL_SERVER_ERROR

        from pronto_shared.jwt_service import create_client_token

        access_token = create_client_token(
            customer_id=cust.id,
            customer_name=cust.name,
            customer_phone=cust.phone,
            table_id=new_sess.table_id,
            session_id=new_sess.id,
        )

        response_data = {
            "success": True,
            "access_token": access_token,
            "data": {
                "session_id": new_sess.id,
                "table_id": new_sess.table_id,
                "anon_id": cust.anon_id,
                "status": new_sess.status,
                "expires_at": new_sess.expires_at.isoformat()
                if new_sess.expires_at
                else None,
            },
        }

        response = make_response(jsonify(response_data), HTTPStatus.OK)

        # Set JWT cookie
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            max_age=86400,  # 24 hours
            path="/",
        )

        return response


@sessions_bp.get("/sessions/validate")
def validate_session():
    """Validate an existing session."""
    session_id = request.args.get("session_id", type=int)
    table_id = request.args.get("table_id", type=int)

    if not session_id or not table_id:
        return jsonify(
            {"valid": False, "error": "Parámetros faltantes"}
        ), HTTPStatus.BAD_REQUEST

    with get_session() as db:
        ds = db.query(DiningSession).filter(DiningSession.id == session_id).first()
        if not ds:
            return jsonify(
                {"valid": False, "error": "Sesión no encontrada"}
            ), HTTPStatus.OK

        if ds.table_id != table_id:
            return jsonify(
                {"valid": False, "error": "table_id no coincide"}
            ), HTTPStatus.OK

        if ds.status != "open":
            return jsonify(
                {"valid": False, "error": f"Sesión {ds.status}"}
            ), HTTPStatus.OK

        if ds.is_expired:
            ds.status = "closed"
            db.commit()
            return jsonify({"valid": False, "error": "Sesión expirada"}), HTTPStatus.OK

        return jsonify(
            {
                "valid": True,
                "session": {
                    "id": ds.id,
                    "table_id": ds.table_id,
                    "status": ds.status,
                    "expires_at": ds.expires_at.isoformat() if ds.expires_at else None,
                },
            }
        ), HTTPStatus.OK


@sessions_bp.post("/sessions/merge")
def merge_sessions():
    """Merge two dining sessions (combine bills from different tables)."""
    payload = request.get_json(silent=True) or {}
    source_session_id = payload.get("source_session_id")
    target_session_id = payload.get("target_session_id")

    if not source_session_id or not target_session_id:
        return jsonify(
            {"error": "Both source and target session IDs are required"}
        ), HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        source = db_session.get(DiningSession, source_session_id)
        target = db_session.get(DiningSession, target_session_id)

        if not source or not target:
            return jsonify(
                {"error": "One or both sessions not found"}
            ), HTTPStatus.NOT_FOUND

        if source.status != "open" or target.status != "open":
            return jsonify(
                {"error": "Both sessions must be open"}
            ), HTTPStatus.BAD_REQUEST

        for order in source.orders:
            order.session_id = target_session_id

        target.recompute_totals()
        source.status = "merged"
        source.closed_at = datetime.now(timezone.utc)

        db_session.commit()

        return jsonify(
            {
                "status": "ok",
                "message": f"Session {source_session_id} merged into {target_session_id}",
                "target_session_id": target_session_id,
                "new_total": float(target.total_amount),
            }
        ), HTTPStatus.OK


@sessions_bp.post("/sessions/<int:session_id>/split")
def split_session(session_id: int):
    """Create split bills for a dining session."""
    payload = request.get_json(silent=True) or {}
    num_splits = payload.get("num_splits", 2)

    if num_splits < 2:
        return jsonify(
            {"error": "Must split into at least 2 parts"}
        ), HTTPStatus.BAD_REQUEST

    with get_session() as db_session:
        session = db_session.get(DiningSession, session_id)

        if not session:
            return jsonify({"error": "Session not found"}), HTTPStatus.NOT_FOUND

        if session.status != "open":
            return jsonify(
                {"error": "Session must be open to split"}
            ), HTTPStatus.BAD_REQUEST

        total = float(session.total_amount)
        split_amount = round(total / num_splits, 2)

        splits = [split_amount] * (num_splits - 1)
        splits.append(round(total - sum(splits), 2))

        return jsonify(
            {
                "status": "ok",
                "session_id": session_id,
                "total_amount": total,
                "num_splits": num_splits,
                "split_amounts": splits,
            }
        ), HTTPStatus.OK
