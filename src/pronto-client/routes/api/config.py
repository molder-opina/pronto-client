"""
Configuration endpoints for clients API.
"""

from http import HTTPStatus

from flask import Blueprint, jsonify

config_bp = Blueprint("client_config", __name__)


@config_bp.get("/tables")
def get_tables():
    """Return active tables for table selection."""
    from sqlalchemy import select, join

    from shared.db import get_session
    from shared.models import Area, Table

    try:
        with get_session() as session:
            results = session.execute(
                select(Table, Area)
                .join(Area, Table.area_id == Area.id)
                .where(Table.is_active)
                .order_by(Area.prefix, Area.name, Table.table_number)
            ).all()

        payload = [
            {
                "id": table.id,
                "table_number": table.table_number,
                "qr_code": table.qr_code,
                "area": {
                    "id": area.id,
                    "prefix": area.prefix,
                    "name": area.name,
                },
            }
            for table, area in results
        ]
        return jsonify({"tables": payload}), HTTPStatus.OK
    except Exception:
        return jsonify({"tables": []}), HTTPStatus.OK


@config_bp.get("/config/<string:config_key>")
def get_config(config_key: str):
    """Get a single configuration parameter by key."""
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import BusinessConfig

    with get_session() as session:
        config = (
            session.execute(select(BusinessConfig).where(BusinessConfig.config_key == config_key))
            .scalars()
            .one_or_none()
        )

        if not config:
            defaults = {
                "waiter_call_timeout_seconds": {"value": "60", "type": "int", "unit": "seconds"}
            }
            if config_key in defaults:
                default = defaults[config_key]
                return jsonify(
                    {
                        "key": config_key,
                        "value": default["value"],
                        "value_type": default["type"],
                        "unit": default["unit"],
                    }
                )
            return jsonify({"error": "Configuración no encontrada"}), HTTPStatus.NOT_FOUND

        return jsonify(
            {
                "key": config.config_key,
                "value": config.config_value,
                "value_type": config.value_type,
                "unit": config.unit,
            }
        )


@config_bp.get("/table-info/<string:qr_code>")
def get_table_by_qr(qr_code: str):
    """Get table information by QR code."""
    from sqlalchemy import select

    from shared.db import get_session
    from shared.models import Table

    with get_session() as session:
        table = (
            session.execute(select(Table).where(Table.qr_code == qr_code, Table.is_active))
            .scalars()
            .one_or_none()
        )

        if not table:
            return jsonify({"error": "Mesa no encontrada"}), HTTPStatus.NOT_FOUND

        return jsonify(
            {
                "id": table.id,
                "table_number": table.table_number,
                "area_id": table.area_id,
                "capacity": table.capacity,
                "status": table.status,
            }
        )
