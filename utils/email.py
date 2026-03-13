import logging

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import settings

logger = logging.getLogger(__name__)


async def send_invitation_email(to_email: str, role: str, link: str) -> None:
    role_display = role.replace("_", " ").title()
    subject = f"You've been invited to Marketing Platform as {role_display}"
    html = f"""
    <html><body>
    <h2>You're invited!</h2>
    <p>You have been invited to join the Marketing Platform as a <strong>{role_display}</strong>.</p>
    <p>Click the link below to set up your account. This link expires in 72 hours.</p>
    <p><a href="{link}">Accept Invitation</a></p>
    <p>If you did not expect this invitation, you can safely ignore this email.</p>
    </body></html>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email
    message.attach(MIMEText(html, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASS or None,
        )
    except Exception as exc:
        logger.error(
            "Failed to send invitation email to %s: %s", to_email, exc, exc_info=exc
        )
        # Do not re-raise — invitation row is already created; admin can resend.
