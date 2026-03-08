# ruff: noqa: E402

import os
import sys
import types
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("PRONTO_ROUTES_ONLY", "1")

if "flask_wtf.csrf" not in sys.modules:
    flask_wtf_module = types.ModuleType("flask_wtf")
    csrf_module = types.ModuleType("flask_wtf.csrf")

    class _CSRFProtect:
        def init_app(self, _app):
            return None

        def protect(self):
            return None

        def exempt(self, func):
            return func

    csrf_module.CSRFProtect = _CSRFProtect
    csrf_module.generate_csrf = lambda: "test-csrf-token"
    flask_wtf_module.csrf = csrf_module
    sys.modules["flask_wtf"] = flask_wtf_module
    sys.modules["flask_wtf.csrf"] = csrf_module

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pronto-client" / "src"))
sys.path.insert(0, str(ROOT / "pronto-libs" / "src"))

from pronto_clients.app import create_app


class _FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 3, 2, 10, 0, tzinfo=tz)


def _client_app():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_business_info_requires_authenticated_customer_session():
    client = _client_app()

    response = client.get("/api/business-info")

    assert response.status_code == 401
    assert response.get_json()["status"] == "error"


def test_business_info_returns_schedule_for_authenticated_customer():
    client = _client_app()
    with client.session_transaction() as flask_session:
        flask_session["customer_ref"] = str(uuid.uuid4())

    with (
        patch(
            "pronto_clients.routes.api.business_info.customer_session_store.get_customer",
            return_value={"customer_id": str(uuid.uuid4()), "name": "Cliente"},
        ),
        patch(
            "pronto_clients.routes.api.business_info.BusinessInfoService.get_business_info",
            return_value={
                "status": "success",
                "data": {
                    "business_name": "Pronto Centro",
                    "timezone": "America/Mexico_City",
                },
            },
        ),
        patch(
            "pronto_clients.routes.api.business_info.BusinessScheduleService.get_schedule",
            return_value={
                "status": "success",
                "data": {
                    "schedules": [
                        {
                            "day_of_week": 0,
                            "is_open": True,
                            "open_time": "09:00",
                            "close_time": "18:00",
                        }
                    ]
                },
            },
        ),
        patch("pronto_clients.routes.api.business_info.datetime", _FixedDateTime),
    ):
        response = client.get("/api/business-info")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["business_name"] == "Pronto Centro"
    assert payload["is_currently_open"] is True
    assert payload["current_day_schedule"]["day_of_week"] == 0
    assert payload["schedule"][0]["open_time"] == "09:00"

