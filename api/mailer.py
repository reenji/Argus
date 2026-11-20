"""Outgoing mail for account emails, over SMTP (for example Brevo's relay)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

logger = logging.getLogger("argus.mail")

# Messages "sent" while no SMTP server is configured, for tests and local runs.
outbox: list[EmailMessage] = []


def verification_enabled() -> bool:
    return bool(settings.smtp_host)


def _deliver(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from or "ARGUS <no-reply@localhost>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if not settings.smtp_host:
        outbox.append(message)
        return
    try:
        await asyncio.to_thread(_deliver, message)
    except (OSError, smtplib.SMTPException) as exc:
        # The caller answers the same either way; a lost email is logged, not shown.
        logger.error("mail_delivery_failed", extra={"error": type(exc).__name__})
