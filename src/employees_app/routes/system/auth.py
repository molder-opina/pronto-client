"""
System console routes for system (formerly super_admin).
Provides reauth flow for quick access to other scopes.
Uses JWT for authentication.
"""

import hashlib
import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import delete

from shared.extensions import csrf
from shared.datetime_utils import utcnow
from shared.db import get_session
from shared.jwt_middleware import get_current_user
from shared.jwt_service import create_access_token, create_refresh_token
from shared.models import AuditLog, Employee, SuperAdminHandoffToken
from shared.scope_guard import ScopeGuard
from shared.services.status_label_service import get_all_status_labels, update_status_label

system_bp = Blueprint(
    "system_app", __name__, url_prefix="/system", template_folder="../../templates/system"
)


@system_bp.before_request
def system_guard():
    """Guard for system scope - only system access."""
    return ScopeGuard(app_scope="system", login_route="system_app.login")()


@system_bp.route("/login", methods=["GET"])
def login():
    """System login page - system only."""
    user = get_current_user()
    if user and user.get("active_scope") == "system":
        return redirect(url_for("system_app.dashboard"))
    return render_template("login_system.html")


@system_bp.route("/login", methods=["POST"], endpoint="process_login")
@csrf.exempt
def process_login():
    """Process system login - super_admin only."""
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return render_template("login_system.html", error="Credenciales requeridas")

    try:
        with get_session() as db_session:
            from shared.security import hash_identifier

            email_hash = hash_identifier(email)
            employee = db_session.query(Employee).filter_by(email_hash=email_hash).first()

            if not employee or not employee.verify_password(password):
                return render_template("login_system.html", error="Credenciales inválidas")

            if not employee.has_scope("system"):
                return render_template(
                    "login_system.html",
                    error="Solo personal del sistema puede acceder a esta consola",
                )

            # Create JWT tokens
            access_token = create_access_token(
                employee_id=employee.id,
                employee_name=employee.name,
                employee_email=email,
                employee_role=employee.role,
                employee_additional_roles=employee.additional_roles,
                active_scope="system",
            )
            refresh_token = create_refresh_token(employee_id=employee.id)

            # Mark employee as signed in
            employee.sign_in()
            db_session.commit()

            response = make_response(redirect(url_for("system_app.dashboard")))
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=86400,
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                secure=request.is_secure,
                samesite="Lax",
                max_age=604800,
                path="/",
            )
            return response

    except Exception as e:
        current_app.logger.error(f"System login error: {e}")
        return render_template("login_system.html", error="Error de sistema")


@system_bp.route("/dashboard")
def dashboard():
    """System dashboard for system role."""
    user = get_current_user()
    employee_id = user.get("employee_id") if user else None
    employee_name = user.get("employee_name") if user else None
    employee_role = user.get("employee_role", "system") if user else "system"

    available_scopes = []
    with get_session() as db_session:
        employee = db_session.query(Employee).filter_by(id=employee_id).first()
        if employee:
            if employee.has_scope("waiter"):
                available_scopes.append({"name": "waiter", "label": "Mesero"})
            if employee.has_scope("chef"):
                available_scopes.append({"name": "chef", "label": "Chef"})
            if employee.has_scope("cashier"):
                available_scopes.append({"name": "cashier", "label": "Cajero"})
            if employee.has_scope("admin"):
                available_scopes.append({"name": "admin", "label": "Admin"})

    return render_template(
        "dashboard_system.html",
        app_context="System",
        employee_id=employee_id,
        employee_name=employee_name,
        employee_role=employee_role,
        available_scopes=available_scopes,
    )


@system_bp.route("/reauth", methods=["GET"], endpoint="reauth_confirm")
def reauth_confirm():
    """Confirmation page for reauth to another scope."""
    target_scope = request.args.get("to")
    valid_scopes = ["waiter", "chef", "cashier", "admin"]

    if not target_scope or target_scope not in valid_scopes:
        return redirect(url_for("system_app.dashboard"))

    user = get_current_user()
    employee_id = user.get("employee_id") if user else None
    if not employee_id:
        return redirect(url_for("system_app.login"))

    with get_session() as db_session:
        employee = db_session.query(Employee).filter_by(id=employee_id).first()
        if not employee or not employee.has_scope(target_scope):
            return redirect(url_for("system_app.dashboard"))

    return render_template(
        "system_reauth_confirm.html",
        target_scope=target_scope,
        employee_name=user.get("employee_name") if user else None,
    )


@system_bp.route("/reauth", methods=["POST"], endpoint="reauth_execute")
def reauth_execute():
    """Execute reauth to another scope."""
    target_scope = request.form.get("target_scope")
    valid_scopes = ["waiter", "chef", "cashier", "admin"]

    if not target_scope or target_scope not in valid_scopes:
        return redirect(url_for("system_app.dashboard"))

    user = get_current_user()
    employee_id = user.get("employee_id") if user else None
    if not employee_id:
        return redirect(url_for("system_app.login"))

    # Origin/Referer validation
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "")
    allowed_hosts = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]

    expected_host = request.host
    if not allowed_hosts:
        allowed_hosts = [expected_host]

    origin_valid = False
    if origin:
        parsed = urlparse(origin)
        netloc = parsed.netloc
        if "@" in netloc:
            netloc = netloc.split("@")[-1]
        origin_valid = netloc in allowed_hosts

    if not origin_valid and referer:
        parsed = urlparse(referer)
        netloc = parsed.netloc
        if "@" in netloc:
            netloc = netloc.split("@")[-1]
        origin_valid = netloc in allowed_hosts

    if not origin_valid:
        if not current_app.config.get("DEBUG_MODE", False):
            current_app.logger.warning(
                f"Reauth blocked - invalid origin/referer. "
                f"Origin={origin}, Referer={referer}, Allowed={allowed_hosts}"
            )
            return redirect(url_for("system_app.dashboard"))
        else:
            current_app.logger.warning(
                f"Reauth warning - no origin/referer (debug mode allows). "
                f"Origin={origin}, Referer={referer}"
            )

    try:
        with get_session() as db_session:
            employee = db_session.query(Employee).filter_by(id=employee_id).first()
            if not employee or not employee.has_scope(target_scope):
                return redirect(url_for("system_app.dashboard"))

            import secrets

            raw_token = secrets.token_urlsafe(32)

            pepper = os.getenv("HANDOFF_PEPPER", "")
            token_hash = hashlib.sha256((raw_token + pepper).encode()).hexdigest()

            token_record = SuperAdminHandoffToken(
                token_hash=token_hash,
                employee_id=employee.id,
                target_scope=target_scope,
                expires_at=utcnow() + timedelta(seconds=60),
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            db_session.add(token_record)
            db_session.flush()

            import json

            audit_details = json.dumps(
                {"scope_from": "system", "scope_to": target_scope, "token_id": token_record.id}
            )

            audit = AuditLog(
                employee_id=employee.id,
                action="reauth_token_generated",
                details=audit_details,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )
            db_session.add(audit)
            db_session.commit()

            current_app.logger.info(
                f"Reauth token generated: employee_id={employee.id}, "
                f"target={target_scope}, token_id={token_record.id}"
            )

            db_session.execute(
                delete(SuperAdminHandoffToken).where(SuperAdminHandoffToken.expires_at < utcnow())
            )
            db_session.commit()

            target_url = url_for(f"{target_scope}_app.system_login")
            return render_template(
                "system_reauth_redirect.html", target_url=target_url, token=raw_token
            )

    except Exception as e:
        current_app.logger.error(f"Reauth error: {e}")
        return redirect(url_for("system_app.dashboard"))


@system_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Logout from system console."""
    user = get_current_user()
    if user:
        try:
            with get_session() as db:
                employee = db.query(Employee).filter(Employee.id == user.get("employee_id")).first()
                if employee:
                    employee.sign_out()
                    db.commit()
        except Exception as e:
            current_app.logger.error(f"Error signing out system employee in DB: {e}")

    response = make_response(redirect(url_for("system_app.login")))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return response


@system_bp.route("/config/order-status-labels", methods=["GET"])
def get_order_status_labels():
    user = get_current_user()
    if not user or user.get("active_scope") != "system":
        return jsonify({"error": "Forbidden"}), 403

    labels = get_all_status_labels()
    accept_header = request.headers.get("Accept", "")
    if "text/html" in accept_header and "application/json" not in accept_header:
        return render_template("system_order_status_labels.html", labels=labels)

    return jsonify({"labels": labels}), 200


@system_bp.route("/config/order-status-labels/<status_key>", methods=["PUT"])
def put_order_status_label(status_key: str):
    user = get_current_user()
    if not user or user.get("active_scope") != "system":
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    client_label = (payload.get("client_label") or "").strip()
    employee_label = (payload.get("employee_label") or "").strip()
    admin_desc = (payload.get("admin_desc") or "").strip()

    if not client_label or not employee_label or not admin_desc:
        return jsonify({"error": "Campos requeridos"}), 400

    response, status = update_status_label(
        status_key=status_key,
        client_label=client_label,
        employee_label=employee_label,
        admin_desc=admin_desc,
        updated_by=user.get("employee_id"),
    )
    return jsonify(response), status
