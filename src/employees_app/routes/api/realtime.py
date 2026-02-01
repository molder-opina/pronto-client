"""
Endpoints de compatibilidad para eventos en tiempo real.

Primero intenta leer eventos del stream de Redis (más rápido).
Si Redis no está disponible, usa PostgreSQL como respaldo.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from employees_app.decorators import login_required
from shared.jwt_middleware import jwt_required

realtime_bp = Blueprint("realtime", __name__)
DEFAULT_LIMIT = 100
HARD_LIMIT = 250


@realtime_bp.get("/realtime/events")
@jwt_required
def get_realtime_events():
    """
    Regresa los eventos almacenados en el stream de Redis (o PostgreSQL como respaldo).
    """
    after_id = request.args.get("after_id") or "0-0"
    requested_limit = request.args.get("limit", type=int)
    limit = min(requested_limit or DEFAULT_LIMIT, HARD_LIMIT)

    # Try Redis stream first (faster, real-time)
    try:
        from shared.socketio_manager import read_events_from_stream as redis_read

        last_id, events = redis_read(after_id=after_id, count=limit)
        if events:
            return jsonify({"events": events, "last_id": last_id, "source": "redis"})
    except Exception:
        pass  # Fall back to PostgreSQL

    # Fallback to PostgreSQL
    try:
        from shared.supabase.realtime import read_events_from_stream as pg_read

        last_id, events = pg_read(after_id=after_id, count=limit)
        return jsonify({"events": events, "last_id": last_id, "source": "postgres"})
    except Exception as e:
        return jsonify({"events": [], "last_id": after_id, "error": str(e)})


__all__ = ["realtime_bp"]
