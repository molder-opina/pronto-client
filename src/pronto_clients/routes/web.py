"""
Customer facing web views rendered via Jinja templates.
"""

from __future__ import annotations

import os
from uuid import UUID
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select
from pronto_shared.trazabilidad import get_logger

from pronto_shared.db import get_session
from pronto_shared.models import DiningSession
from pronto_shared.services.customer_service import (
    get_customer_by_email,
)
from pronto_shared.services.customer_session_store import (
    customer_session_store,
    RedisUnavailableError,
)

web_bp = Blueprint("client_web", __name__)

_KIOSK_SECRET = os.getenv("PRONTO_KIOSK_SECRET", "")
# Kiosk password: use env var or generate random (must be configured in production)
_KIOSK_PASSWORD = os.getenv("PRONTO_KIOSK_PASSWORD") or os.urandom(16).hex()
logger = get_logger("clients.web")


def _get_current_customer() -> dict | None:
    customer_ref = session.get("customer_ref")
    if not customer_ref:
        return None

    try:
        return customer_session_store.get_customer(customer_ref)
    except RedisUnavailableError:
        logger.warning(
            "Customer session store unavailable while resolving web customer"
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Unexpected error resolving customer session",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        return None


def _build_next_url() -> str:
    return request.full_path.rstrip("?") if request.query_string else request.path


def _redirect_to_auth(tab: str = "login"):
    endpoint = (
        "client_web.register_page" if tab == "register" else "client_web.login_page"
    )
    return redirect(url_for(endpoint, next=_build_next_url()))


def _require_customer_web_auth():
    customer = _get_current_customer()
    if customer:
        return customer, None
    return None, _redirect_to_auth("login")


def _is_authorized_kiosk_bootstrap(location: str):
    debug_mode = bool(current_app.config.get("DEBUG_MODE", False))
    provided_secret = request.headers.get("X-PRONTO-KIOSK-SECRET", "")

    if _KIOSK_SECRET:
        if provided_secret != _KIOSK_SECRET:
            logger.warning(
                "kiosk secret mismatch",
                extra={"location": location, "remote_addr": request.remote_addr},
            )
            return jsonify({"error": "Unauthorized"}), 401
        return None

    if not debug_mode:
        logger.error(
            "kiosk secret missing in non-debug mode",
            extra={"location": location},
        )
        return jsonify({"error": "Kiosk misconfigured"}), 503

    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    source_ip = forwarded_for or request.remote_addr or ""
    if source_ip not in {"127.0.0.1", "::1", "localhost"}:
        logger.warning(
            "kiosk start blocked in debug due non-local source",
            extra={"location": location, "remote_addr": source_ip},
        )
        return jsonify({"error": "Unauthorized"}), 401

    logger.warning(
        "kiosk start in debug mode without kiosk secret",
        extra={"location": location, "remote_addr": source_ip},
    )
    return None


def _is_matching_kiosk_session(customer: dict | None, location: str) -> bool:
    return bool(
        customer
        and customer.get("kind") == "kiosk"
        and customer.get("kiosk_location") == location
    )


@web_bp.get("/login")
def login_page():
    current_customer = _get_current_customer()
    next_url = request.args.get("next") or "/"
    if current_customer:
        return redirect(next_url)

    return redirect(
        url_for("client_web.home", view="profile", tab="login", next=next_url)
    )


@web_bp.get("/register")
def register_page():
    current_customer = _get_current_customer()
    next_url = request.args.get("next") or "/"
    if current_customer:
        return redirect(next_url)

    return redirect(
        url_for("client_web.home", view="profile", tab="register", next=next_url)
    )


@web_bp.get("/")
def home():
    """
    Landing page that consumes the API via HTMX/fetch for a richer experience.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    # Business rule: menu/home must be accessible without authentication.
    # Authentication is requested later when the customer confirms/places an order.
    customer_data = _get_current_customer()

    # Fetch available tables for debug panel
    available_tables = []
    if debug_auto_table or True:  # Always fetch for now to support debug panel
        try:
            from pronto_shared.models import Table, Area

            with get_session() as db_session:
                results = db_session.execute(
                    select(Table, Area)
                    .join(Area, Table.area_id == Area.id)
                    .order_by(Area.prefix, Area.name, Table.table_number)
                ).all()
                available_tables = [
                    {
                        "table_number": t.table_number,
                        "area": {"prefix": a.prefix, "name": a.name},
                        "id": t.id,
                    }
                    for t, a in results
                ]
        except Exception as e:
            logger.error(
                f"Error fetching tables for debug: {e}", error={"message": str(e)}
            )

    return render_template(
        "index.html",
        debug_auto_table=debug_auto_table,
        customer_data=customer_data,
        available_tables=available_tables,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/mesa/<string:qr_code>")
def mesa_qr(qr_code: str):
    """
    QR code entry point for physical restaurant tables.

    Resolves the QR code to a table UUID and redirects to the home page
    with the correct table_id query parameter so the session is initialized.

    Args:
        qr_code: The QR code printed on the physical table (e.g. 'M1-QR-SEED')
    """
    from pronto_shared.models import Table
    from sqlalchemy import select

    with get_session() as db_session:
        stmt = select(Table).where(Table.qr_code == qr_code, Table.is_active == True)  # noqa: E712
        table = db_session.execute(stmt).scalars().one_or_none()

    if not table:
        logger.warning(
            "QR code not found or table inactive",
            extra={"qr_code": qr_code},
        )
        return redirect(url_for("client_web.home"))

    target_url = url_for("client_web.home", table_id=str(table.id))
    logger.info(
        "QR scan redirect",
        extra={"qr_code": qr_code, "table_id": str(table.id), "table_number": table.table_number},
    )
    return redirect(target_url)


@web_bp.get("/checkout")
def checkout():
    """
    Checkout page for finalizing the order.
    Separated from the menu page for better UX and cleaner code organization.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    customer_data, auth_redirect = _require_customer_web_auth()
    if auth_redirect:
        return auth_redirect

    return redirect(url_for("client_web.home", view="details"))


@web_bp.get("/menu-alt")
def menu_alt():
    """
    Alternative menu design with modern delivery app layout.
    """
    debug_auto_table = current_app.config.get("DEBUG_AUTO_TABLE", False)
    customer_data, auth_redirect = _require_customer_web_auth()
    if auth_redirect:
        return auth_redirect

    return redirect(url_for("client_web.home"))


@web_bp.get("/feedback")
def feedback_form():
    """
    Feedback form for customers to rate their experience.

    Query params:
        - session_id: The dining session ID (optional, uses Flask session if available)
        - employee_id: The waiter/employee ID (optional)
    """
    current_customer, auth_redirect = _require_customer_web_auth()
    if auth_redirect:
        return auth_redirect

    session_id_raw = request.args.get("session_id") or session.get("dining_session_id")
    employee_id_raw = request.args.get("employee_id")

    if not session_id_raw:
        return "Session ID requerido", 400

    try:
        session_id = UUID(str(session_id_raw))
    except (TypeError, ValueError):
        return "Session ID inválido", 400

    employee_id = None
    if employee_id_raw:
        try:
            employee_id = UUID(str(employee_id_raw))
        except (TypeError, ValueError):
            return "Employee ID inválido", 400

    # Verify session exists
    with get_session() as db_session:
        stmt = select(DiningSession).where(DiningSession.id == session_id)
        dining_session = db_session.execute(stmt).scalars().one_or_none()

        current_customer_id = current_customer.get("customer_id")
        if (
            not dining_session
            or not current_customer_id
            or str(dining_session.customer_id) != str(current_customer_id)
        ):
            return "Sesión no encontrada", 404

    return render_template(
        "feedback.html",
        session_id=str(session_id),
        employee_id=str(employee_id) if employee_id else "",
        feedback_api_base_url=current_app.config.get("EMPLOYEE_API_BASE_URL"),
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.get("/kiosk/<location>")
def kiosk_screen(location: str):
    """
    Kiosk welcome screen for self-service ordering.

    Args:
        location: Kiosk location identifier (e.g., 'lobby', 'entrance')
    """
    current_customer = _get_current_customer()
    if not _is_matching_kiosk_session(current_customer, location):
        kiosk_auth_error = _is_authorized_kiosk_bootstrap(location)
        if kiosk_auth_error:
            return kiosk_auth_error

    return render_template(
        "kiosk.html",
        location=location,
        api_base_url=current_app.config.get("API_BASE_URL", ""),
    )


@web_bp.post("/kiosk/<location>/start")
def kiosk_start(location: str):
    """
    Auto-login for kiosk account.

    Creates or retrieves kiosk customer account for the location.
    Sets customer_ref in session.

    Security:
        - In production: requires PRONTO_KIOSK_SECRET header
        - In dev mode: no secret required
    """
    kiosk_auth_error = _is_authorized_kiosk_bootstrap(location)
    if kiosk_auth_error:
        return kiosk_auth_error

    kiosk_email = f"kiosk+{location}@pronto.local"

    with get_session() as db:
        customer = get_customer_by_email(db, kiosk_email)

        if not customer:
            from pronto_shared.services.customer_service import create_customer

            try:
                customer = create_customer(
                    db,
                    first_name=f"Kiosk {location}",
                    email=kiosk_email,
                    password=_KIOSK_PASSWORD,
                    kind="kiosk",
                    kiosk_location=location,
                )
            except ValueError:
                customer = get_customer_by_email(db, kiosk_email)
                if not customer:
                    return jsonify({"error": "Failed to create kiosk account"}), 500

    try:
        customer_ref = customer_session_store.create_customer_ref(
            customer_id=customer["id"],
            email=customer["email"],
            name=customer["first_name"],
            kind="kiosk",
            kiosk_location=location,
        )
    except RedisUnavailableError:
        return jsonify({"error": "Service unavailable"}), 503

    session["customer_ref"] = customer_ref
    session.permanent = False

    return jsonify(
        {
            "success": True,
            "customer": {
                "id": customer["id"],
                "name": customer["first_name"],
                "kind": "kiosk",
                "location": location,
            },
        }
    )


@web_bp.get("/terms-of-service")
def terms_of_service():
    """Terms of Service page."""
    return render_template("terms-of-service.html")


@web_bp.get("/privacy-policy")
def privacy_policy():
    """Privacy Policy page."""
    return render_template("privacy-policy.html")

