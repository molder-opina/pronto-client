"""
Areas endpoints for clients API.

Client UI modules expect /api/areas for table selection.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify

areas_bp = Blueprint("client_areas", __name__)


@areas_bp.get("/areas")
def list_areas():
    from sqlalchemy import select

    from pronto_shared.db import get_session
    from pronto_shared.models import Area

    try:
        with get_session() as session:
            rows = (
                session.execute(select(Area).where(Area.is_active).order_by(Area.prefix, Area.name))
                .scalars()
                .all()
            )
        payload = [{"id": a.id, "prefix": a.prefix, "name": a.name} for a in rows]
        return jsonify({"areas": payload}), HTTPStatus.OK
    except Exception:
        return jsonify({"areas": []}), HTTPStatus.OK

