"""
Order status label catalog service (system only).
"""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus

from shared.db import get_session
from shared.models import OrderStatusLabel
from shared.serializers import invalidate_status_label_cache


def get_all_status_labels() -> list[dict[str, object]]:
    with get_session() as session:
        labels = session.query(OrderStatusLabel).order_by(OrderStatusLabel.status_key).all()
        return [
            {
                "status_key": label.status_key,
                "client_label": label.client_label,
                "employee_label": label.employee_label,
                "admin_desc": label.admin_desc,
                "updated_at": label.updated_at.isoformat(),
                "updated_by_emp_id": label.updated_by_emp_id,
                "version": label.version,
            }
            for label in labels
        ]


def update_status_label(
    status_key: str,
    client_label: str,
    employee_label: str,
    admin_desc: str,
    updated_by: int | None = None,
) -> tuple[dict[str, object], HTTPStatus]:
    with get_session() as session:
        label = session.get(OrderStatusLabel, status_key)
        if not label:
            return {"error": "Status no encontrado"}, HTTPStatus.NOT_FOUND

        label.client_label = client_label
        label.employee_label = employee_label
        label.admin_desc = admin_desc
        label.updated_by_emp_id = updated_by
        label.updated_at = datetime.utcnow()
        label.version = (label.version or 0) + 1

        session.add(label)
        session.commit()

        invalidate_status_label_cache(status_key)

        return {
            "message": "Label actualizado",
            "status_key": status_key,
            "version": label.version,
        }, HTTPStatus.OK
