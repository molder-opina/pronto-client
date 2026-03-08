import os
import sys
import types
import uuid
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


def _client_app():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_home_renders_for_anonymous_customer():
    client = _client_app()
    with patch("pronto_clients.routes.web.render_template", return_value="landing-page") as render_mock:
        response = client.get("/")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "landing-page"
    render_mock.assert_called_once()


def test_login_page_redirects_anonymous_customer_to_profile_login_tab():
    client = _client_app()
    response = client.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/?view=profile&tab=login")


def test_home_renders_when_customer_session_exists():
    client = _client_app()
    with client.session_transaction() as flask_session:
        flask_session["customer_ref"] = str(uuid.uuid4())

    with (
        patch(
            "pronto_clients.routes.web.customer_session_store.get_customer",
            return_value={"customer_id": str(uuid.uuid4()), "name": "Cliente"},
        ),
        patch("pronto_clients.routes.web.render_template", return_value="menu-page") as render_mock,
        patch("pronto_clients.routes.web.get_session") as get_session_mock,
    ):
        get_session_mock.side_effect = RuntimeError("db should not be used in routes-only test")
        response = client.get("/")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "menu-page"
    render_mock.assert_called_once()


def test_feedback_requires_authenticated_customer_ownership():
    client = _client_app()
    session_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    other_customer_id = uuid.uuid4()

    with client.session_transaction() as flask_session:
        flask_session["customer_ref"] = str(uuid.uuid4())

    class _FakeScalarResult:
        def one_or_none(self):
            return type("DiningSessionRecord", (), {"customer_id": other_customer_id})()

    class _FakeExecuteResult:
        def scalars(self):
            return _FakeScalarResult()

    class _FakeDbSession:
        def execute(self, _stmt):
            return _FakeExecuteResult()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with (
        patch(
            "pronto_clients.routes.web.customer_session_store.get_customer",
            return_value={"customer_id": str(customer_id), "name": "Cliente"},
        ),
        patch("pronto_clients.routes.web.get_session", return_value=_FakeDbSession()),
    ):
        response = client.get(f"/feedback?session_id={session_id}")

    assert response.status_code == 404


def test_kiosk_screen_requires_authorized_bootstrap_when_not_authenticated():
    client = _client_app()
    response = client.get("/kiosk/lobby")
    assert response.status_code in {401, 503}


def test_kiosk_screen_allows_matching_authenticated_kiosk_session():
    client = _client_app()
    with client.session_transaction() as flask_session:
        flask_session["customer_ref"] = str(uuid.uuid4())

    with (
        patch(
            "pronto_clients.routes.web.customer_session_store.get_customer",
            return_value={
                "customer_id": str(uuid.uuid4()),
                "name": "Kiosk",
                "kind": "kiosk",
                "kiosk_location": "lobby",
            },
        ),
        patch("pronto_clients.routes.web.render_template", return_value="kiosk-page") as render_mock,
    ):
        response = client.get("/kiosk/lobby")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "kiosk-page"
    render_mock.assert_called_once()