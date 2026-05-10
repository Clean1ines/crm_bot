"""SMTP-backed email delivery adapter."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from src.application.ports.email_port import EmailSenderPort
from src.infrastructure.config.settings import Settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DisabledEmailSender:
    @property
    def enabled(self) -> bool:
        return False

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> None:
        return None


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_email: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.from_email = from_email
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_email)

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> None:
        if not self.enabled:
            return None

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text)

        if html:
            message.add_alternative(html, subtype="html")

        await asyncio.to_thread(self._send_message, message)

    def _send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(message)


def build_email_sender(settings: Settings) -> EmailSenderPort:
    if settings.EMAIL_DELIVERY_MODE != "smtp":
        return DisabledEmailSender()

    if not settings.SMTP_HOST or not settings.EMAIL_FROM:
        logger.warning(
            "SMTP email delivery requested but not fully configured",
            extra={
                "smtp_host_set": bool(settings.SMTP_HOST),
                "email_from_set": bool(settings.EMAIL_FROM),
            },
        )
        return DisabledEmailSender()

    return SmtpEmailSender(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        from_email=settings.EMAIL_FROM,
        username=settings.SMTP_USERNAME or None,
        password=settings.SMTP_PASSWORD or None,
        use_tls=settings.SMTP_USE_TLS,
        timeout_seconds=settings.SMTP_TIMEOUT_SECONDS,
    )
