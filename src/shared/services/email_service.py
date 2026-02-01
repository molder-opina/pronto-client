"""
Email Service for Pronto App
Handles sending emails via SMTP (SendGrid, Gmail, etc.)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""

    def __init__(self):
        self.enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM", "noreply@pronto.local")
        self.from_name = os.getenv("SMTP_FROM_NAME", "Pronto Restaurante")

    def send_email(
        self, to_email: str, subject: str, body_text: str, body_html: str | None = None
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: Optional HTML body

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(f"[EMAIL] Email disabled. Would send to {to_email}: {subject}")
            return False

        if not self.smtp_password:
            logger.error("[EMAIL] SMTP_PASSWORD not configured")
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            # Attach plain text
            part1 = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part1)

            # Attach HTML if provided
            if body_html:
                part2 = MIMEText(body_html, "html", "utf-8")
                msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info(f"[EMAIL] Sent successfully to {to_email}: {subject}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[EMAIL] Authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"[EMAIL] SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"[EMAIL] Unexpected error: {e}")
            return False

    def send_ticket(
        self,
        to_email: str,
        ticket_text: str,
        session_id: int,
        restaurant_name: str = "Pronto Restaurante",
    ) -> bool:
        """
        Send a ticket via email.

        Args:
            to_email: Recipient email
            ticket_text: The ticket content
            session_id: Session ID for reference
            restaurant_name: Name of the restaurant

        Returns:
            True if sent successfully
        """
        subject = f"Tu ticket de {restaurant_name} - #{session_id}"

        # Plain text version
        body_text = f"""
{restaurant_name}
{"=" * 40}

{ticket_text}

{"=" * 40}
Gracias por tu visita!

Este es un email automático, por favor no responder.
"""

        # HTML version
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1e293b;
            max-width: 500px;
            margin: 0 auto;
            padding: 20px;
        }}
        .ticket-container {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            overflow: hidden;
        }}
        .ticket-header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
            color: white;
            padding: 24px;
            text-align: center;
        }}
        .ticket-header h1 {{
            margin: 0;
            font-size: 1.5rem;
        }}
        .ticket-header p {{
            margin: 8px 0 0;
            opacity: 0.9;
        }}
        .ticket-body {{
            padding: 24px;
            background: #f8fafc;
        }}
        .ticket-content {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            white-space: pre-wrap;
            border: 1px solid #e2e8f0;
        }}
        .ticket-footer {{
            padding: 16px 24px;
            text-align: center;
            background: #f1f5f9;
            color: #64748b;
            font-size: 0.85rem;
        }}
        .thank-you {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 8px;
        }}
    </style>
</head>
<body>
    <div class="ticket-container">
        <div class="ticket-header">
            <h1>{restaurant_name}</h1>
            <p>Ticket #{session_id}</p>
        </div>
        <div class="ticket-body">
            <div class="ticket-content">{ticket_text}</div>
        </div>
        <div class="ticket-footer">
            <p class="thank-you">Gracias por tu visita!</p>
            <p>Este es un email automatico, por favor no responder.</p>
        </div>
    </div>
</body>
</html>
"""

        return self.send_email(to_email, subject, body_text, body_html)


# Global instance
email_service = EmailService()


def send_ticket_email(to_email: str, ticket_text: str, session_id: int) -> bool:
    """
    Convenience function to send a ticket email.

    Args:
        to_email: Recipient email
        ticket_text: Ticket content
        session_id: Session ID

    Returns:
        True if sent successfully
    """
    restaurant_name = os.getenv("RESTAURANT_NAME", "Pronto Restaurante")
    return email_service.send_ticket(to_email, ticket_text, session_id, restaurant_name)


def send_template_email(
    to_email: str, subject: str, html_content: str, template_name: str | None = None
) -> bool:
    """Send a simple HTML email using the shared service."""
    body_text = html_content
    if html_content:
        body_text = "".join(html_content.splitlines())
    return email_service.send_email(to_email, subject, body_text, body_html=html_content)
