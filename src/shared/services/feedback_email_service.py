"""
Feedback email service for handling post-payment feedback via email links.
"""

import secrets
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import and_, select

from shared.db import get_session
from shared.models import DiningSession, Feedback, FeedbackToken, Order


class FeedbackEmailService:
    """Service for managing feedback email links and tokens."""

    @staticmethod
    def get_effective_email_for_order(
        order: Order, session: DiningSession | None = None
    ) -> str | None:
        """
        Determine the effective email for an order/session.
        Rules:
        - Registered user: use user.email
        - Anonymous: look for captured email in order/session (customer_email, session.email, etc.)
        """
        # Registered user has priority
        if order.customer_id and order.customer:
            return order.customer.email

        # Anonymous user - check captured email from session or order
        if session:
            if hasattr(session, "email") and session.email:
                return session.email
            if hasattr(session, "customer_email") and session.customer_email:
                return session.customer_email

        # Check order-level captured email
        if hasattr(order, "customer_email") and order.customer_email:
            return order.customer_email

        return None

    @staticmethod
    def has_existing_feedback_for_order(order_id: int) -> bool:
        """Check if feedback already exists for an order."""
        from sqlalchemy import func

        with get_session() as db_session:
            count = db_session.execute(
                select(func.count(Feedback.id)).where(
                    Feedback.session_id.in_(select(Order.session_id).where(Order.id == order_id))
                )
            ).scalar()
            return count > 0

    @staticmethod
    def has_active_token_for_order(order_id: int) -> FeedbackToken | None:
        """Check if there's an active (not used, not expired) token for an order."""

        with get_session() as db_session:
            return db_session.execute(
                select(FeedbackToken).where(
                    and_(
                        FeedbackToken.order_id == order_id,
                        FeedbackToken.used_at.is_(None),
                        FeedbackToken.expires_at > datetime.utcnow(),
                    )
                )
            ).scalar_one_or_none()

    @staticmethod
    def create_feedback_token(
        order_id: int, session_id: int, user_id: int | None, email: str | None, ttl_hours: int = 24
    ) -> FeedbackToken:
        """Create a feedback token with expiration."""
        token = secrets.token_urlsafe(32)
        token_hash = secrets.sha256_hex(token)

        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        with get_session() as db_session:
            feedback_token = FeedbackToken(
                token_hash=token_hash,
                order_id=order_id,
                session_id=session_id,
                user_id=user_id,
                email=email,
                expires_at=expires_at,
            )
            db_session.add(feedback_token)
            db_session.commit()
            db_session.refresh(feedback_token)

        current_app.logger.info(
            f"Created feedback token for order {order_id}, expires at {expires_at}"
        )
        return feedback_token

    @staticmethod
    def validate_token(token: str) -> dict | None:
        """
        Validate a feedback token and return context.
        Returns dict with order_id, session_id, user_id, email, questions if valid.
        Returns None if invalid or expired.
        """
        token_hash = secrets.sha256_hex(token)

        with get_session() as db_session:
            feedback_token = db_session.execute(
                select(FeedbackToken).where(
                    and_(
                        FeedbackToken.token_hash == token_hash,
                        FeedbackToken.used_at.is_(None),
                        FeedbackToken.expires_at > datetime.utcnow(),
                    )
                )
            ).scalar_one_or_none()

            if not feedback_token:
                current_app.logger.warn(f"Invalid or expired feedback token: {token[:8]}...")
                return None

            # Fetch order and session context
            order = db_session.execute(
                select(Order).where(Order.id == feedback_token.order_id)
            ).scalar_one_or_none()

            if not order:
                current_app.logger.error(
                    f"Order {feedback_token.order_id} not found for feedback token"
                )
                return None

            return {
                "token": token,
                "token_hash": token_hash,
                "order_id": feedback_token.order_id,
                "session_id": feedback_token.session_id,
                "user_id": feedback_token.user_id,
                "email": feedback_token.email,
                "table_number": order.session.table_number if order.session else None,
                "total_amount": float(order.total_amount),
            }

    @staticmethod
    def mark_token_used(token_hash: str) -> bool:
        """Mark a feedback token as used."""
        with get_session() as db_session:
            feedback_token = db_session.execute(
                select(FeedbackToken).where(FeedbackToken.token_hash == token_hash)
            ).scalar_one_or_none()

            if not feedback_token:
                return False

            if feedback_token.used_at:
                return False

            feedback_token.used_at = datetime.utcnow()
            db_session.commit()
            current_app.logger.info(f"Marked feedback token {token_hash[:8]}... as used")
            return True

    @staticmethod
    def should_send_feedback_email(
        order_id: int,
        is_registered: bool,
        has_email: bool,
        email_enabled: bool = True,
        allow_anonymous_if_email: bool = True,
    ) -> bool:
        """
        Determine if feedback email should be sent based on rules.
        """
        # Email feedback disabled globally
        if not email_enabled:
            current_app.logger.info(
                f"Feedback email disabled globally, skipping for order {order_id}"
            )
            return False

        # Feedback already submitted
        if FeedbackEmailService.has_existing_feedback_for_order(order_id):
            current_app.logger.info(f"Feedback already exists for order {order_id}, skipping email")
            return False

        # Already has active token (throttling)
        if FeedbackEmailService.has_active_token_for_order(order_id):
            current_app.logger.info(
                f"Active feedback token exists for order {order_id}, skipping email"
            )
            return False

        # No effective email available
        if not has_email:
            current_app.logger.info(f"No effective email for order {order_id}, skipping email")
            return False

        # Anonymous user with email: check if allowed
        if not is_registered and has_email:
            return allow_anonymous_if_email

        # Registered user: always send (if has email)
        if is_registered:
            return has_email

        return False

    @staticmethod
    def trigger_feedback_email(
        order_id: int, session_id: int, timeout_seconds: int = 10, ttl_hours: int = 24
    ) -> dict:
        """
        Trigger feedback email after timer expires.
        Called from frontend when feedback prompt times out.

        Returns:
        - {"success": bool, "email_sent": bool, "message": str}
        """
        from shared.services.business_config_service import ConfigService

        with get_session() as db_session:
            # Fetch order and session
            order = db_session.execute(
                select(Order).where(Order.id == order_id)
            ).scalar_one_or_none()

            if not order:
                return {"success": False, "message": "Orden no encontrada"}

            # Check if order is paid
            if not order.is_paid():
                return {"success": False, "message": "La orden no ha sido pagada"}

            # Get effective email
            session = db_session.execute(
                select(DiningSession).where(DiningSession.id == session_id)
            ).scalar_one_or_none()

            effective_email = FeedbackEmailService.get_effective_email_for_order(order, session)
            has_email = effective_email is not None
            is_registered = order.customer_id is not None

            # Get config
            config = ConfigService()
            email_enabled = config.get_bool("feedback_email_enabled", True)
            allow_anonymous = config.get_bool(
                "feedback_email_allow_anonymous_if_email_present", True
            )

            # Determine if email should be sent
            should_send = FeedbackEmailService.should_send_feedback_email(
                order_id=order_id,
                is_registered=is_registered,
                has_email=has_email,
                email_enabled=email_enabled,
                allow_anonymous_if_email=allow_anonymous,
            )

            if not should_send:
                return {
                    "success": True,
                    "email_sent": False,
                    "message": "No se envió email (feedback ya enviado, sin email, o no aplicable)",
                }

            # Create token
            try:
                token_obj = FeedbackEmailService.create_feedback_token(
                    order_id=order_id,
                    session_id=session_id,
                    user_id=order.customer_id,
                    email=effective_email,
                    ttl_hours=ttl_hours,
                )

                # Send email
                email_sent = False
                if effective_email:
                    email_sent = FeedbackEmailService.send_feedback_email(
                        to_email=effective_email,
                        token=token_obj.token_hash,
                        order=order,
                        session=session,
                        config=config,
                    )

                return {
                    "success": True,
                    "email_sent": email_sent,
                    "message": "Email enviado exitosamente" if email_sent else "Email no enviado",
                }

            except Exception as e:
                current_app.logger.error(f"Error triggering feedback email: {e}", exc_info=True)
                return {"success": False, "message": f"Error: {e!s}"}

    @staticmethod
    def send_feedback_email(
        to_email: str, token: str, order: Order, session: DiningSession | None, config
    ) -> bool:
        """Send feedback email with link."""
        from shared.services.email_service import send_template_email

        # Build feedback URL
        base_url = current_app.config.get("BASE_URL", "http://localhost:6080")
        feedback_url = f"{base_url}/feedback/email/{token}"

        # Get template from config
        subject = config.get_string("feedback_email_subject", "¿Qué tal estuvo tu experiencia?")
        body_template = config.get_string(
            "feedback_email_body_template",
            '<p>Gracias por tu visita. Nos gustaría conocer tu opinión:</p><p><a href="{{feedback_url}}">Dejar feedback</a></p>',
        )

        # Render template
        body = body_template.replace("{{feedback_url}}", feedback_url)

        try:
            send_template_email(
                to_email=to_email,
                subject=subject,
                html_content=body,
                template_name="feedback_email",
            )
            return True
        except Exception as e:
            current_app.logger.error(
                f"Error sending feedback email to {to_email}: {e}", exc_info=True
            )
            return False
