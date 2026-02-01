import logging
import time

from flask import Flask, Response, g, request

from shared.jwt_middleware import get_current_user

logger = logging.getLogger("audit")


def init_audit_middleware(app: Flask):
    """
    Registra hooks para auditoría de requests y responses.
    Estándar: USER|ACTION|TYPE|CODE|RETVAL|SESSION|TIME
    """

    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.after_request
    def log_request(response: Response):
        try:
            # 1. User - Obtener del JWT
            try:
                user = get_current_user()
                user_id = user.get("email") if user else "ANONYMOUS"
            except Exception:
                user_id = "ANONYMOUS"

            # 2. Action
            action = f"{request.method} {request.path}"

            # 3. Session ID (Traceability)
            # Intentar obtener de cookie o generar uno temporal para request actual de headers
            session_trace_id = (
                request.cookies.get("session")
                or request.headers.get("X-Request-ID")
                or "NO_SESSION"
            )
            # Recortar si es muy largo (flask session cookie es larga)
            if len(session_trace_id) > 20:
                session_trace_id = session_trace_id[:8] + "..."

            # 4. Time
            duration = 0
            if hasattr(g, "start_time"):
                duration = int((time.time() - g.start_time) * 1000)

            # 5. Status & RetVal
            status_code = response.status_code

            # Safe content length access
            content_length = 0
            if response.direct_passthrough:
                content_length = 0  # Cannot access data in passthrough mode
            else:
                content_length = response.content_length or (
                    len(response.data) if hasattr(response, "data") else 0
                )

            retval = f"{content_length} bytes"

            # Formato Estandarizado Solicitado:
            # usuario|accion|request/response| codigo| retorno de comando o accio| session id para tazabilidad| tiempo de repuesta en ms

            log_line = f"{user_id}|{action}|RESPONSE|{status_code}|{retval}|{session_trace_id}|{duration}ms"

            # Nivel de log: Error si 5xx, Warn si 4xx, Info si 2xx/3xx
            if status_code >= 500:
                logger.error(log_line)
            elif status_code >= 400:
                logger.warning(log_line)
            else:
                logger.info(log_line)

        except Exception as e:
            # Log failure but do not break response
            logger.error(f"SYSTEM|AUDIT_FAIL|ERROR|500|{e!s}|UNKNOWN|0ms")

        return response


def audit_action(action_name: str, details: str = "", status: str = "OK"):
    """
    Registra una acción interna de negocio para trazabilidad profunda.
    Usa el mismo estándar: USER|ACTION|TYPE|CODE|RETVAL|SESSION|TIME
    Type forzado a 'INTERNAL'.
    """
    try:
        # Intentar obtener contexto de Flask si existe
        try:
            # Obtener user del JWT
            user = get_current_user()
            user_id = user.get("email") if user else "ANONYMOUS"
            
            # Session ID estandarizado (corto)
            full_sid = (
                request.cookies.get("session")
                or request.headers.get("X-Request-ID")
                or "NO_SESSION"
            )
            session_trace_id = full_sid[:8] + "..." if len(full_sid) > 20 else full_sid

            duration = 0
            if hasattr(g, "start_time"):
                duration = int((time.time() - g.start_time) * 1000)
        except RuntimeError:
            # Contexto fuera de request (Background tasks, scripts)
            user_id = "SYSTEM"
            session_trace_id = "BACKGROUND"
            duration = 0

        log_line = (
            f"{user_id}|{action_name}|INTERNAL|{status}|{details}|{session_trace_id}|{duration}ms"
        )
        logger.info(log_line)

    except Exception as e:
        # Fallback definitivo
        logger.error(f"SYSTEM|AUDIT_INTERNAL_FAIL|ERROR|500|{e!s}|UNKNOWN|0ms")

    # Capturar excepciones no manejadas para logguearlas antes de que Flask devuelva 500
    # Nota: Flask maneja logs de errores por defecto, pero queremos el formato custom.
    # Usaremos teardown_request para errores que rompen before/after? No, errorhandler es mejor.
    # Pero after_request corre incluso con errores si se manejan via exceptions.
