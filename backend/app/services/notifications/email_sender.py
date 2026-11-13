"""Provider-independent email adapter for notification delivery."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage as PyEmailMessage
import smtplib
import socket
import ssl

from app.core.config import settings


@dataclass
class EmailMessage:
    recipient: str
    subject: str
    body_text: str
    body_html: str
    sender_address: str | None = None
    sender_name: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class EmailSendResult:
    success: bool
    provider: str
    error_message: str | None = None
    is_transient: bool = False
    failure_category: str | None = None
    retry_after_seconds: float | None = None


class EmailSender(ABC):
    """Abstract interface for sending email notifications."""

    @abstractmethod
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Send an email message synchronously."""
        raise NotImplementedError


class TestEmailSender(EmailSender):
    """In-memory safe development and test backend. Never contacts real servers."""

    _sent_messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        if settings.APP_ENV == "production":
            return EmailSendResult(False, "test", "Test adapter forbidden in production",
                                   False, "configuration")
        # Validate recipient format
        if not message.recipient or "@" not in message.recipient:
            return EmailSendResult(
                success=False,
                provider="test",
                error_message="Invalid recipient address",
                is_transient=False,
                failure_category="invalid_recipient",
            )
        self._sent_messages.append(message)
        return EmailSendResult(
            success=True,
            provider="test",
            failure_category=None,
        )

    @classmethod
    def get_sent_messages(cls) -> list[EmailMessage]:
        return list(cls._sent_messages)

    @classmethod
    def clear(cls) -> None:
        cls._sent_messages.clear()


class SmtpEmailSender(EmailSender):
    """Standard SMTP adapter configured via environment variables."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.timeout = timeout

    def send(self, message: EmailMessage) -> EmailSendResult:
        if not message.recipient or "@" not in message.recipient:
            return EmailSendResult(
                success=False,
                provider="smtp",
                error_message="Invalid recipient address",
                is_transient=False,
                failure_category="invalid_recipient",
            )

        msg = PyEmailMessage()
        msg["Subject"] = message.subject
        sender = message.sender_address or settings.EMAIL_SENDER_ADDRESS
        sender_name = message.sender_name or settings.EMAIL_SENDER_NAME
        msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
        msg["To"] = message.recipient

        for k, v in message.headers.items():
            msg[k] = v

        msg.set_content(message.body_text)
        msg.add_alternative(message.body_html, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:

                if self.use_tls:
                    server.starttls(context = ssl.create_default_context())


                if self.username and self.password:
                    server.login(self.username, self.password)


                refused = server.send_message(msg)


                if refused:
                    codes = [value[0] for value in refused.values()]
                    transient = all(400 <= code < 500 for code in codes)
                    return EmailSendResult(False, "smtp", "SMTP recipient refused",
                                           transient, "transient" if transient else "invalid_recipient")
            return EmailSendResult(success=True, provider="smtp")

        except smtplib.SMTPRecipientsRefused as err:
            codes = [value[0] for value in err.recipients.values()]
            transient = bool(codes) and all(400 <= code < 500 for code in codes)
            return EmailSendResult(False, "smtp", "SMTP recipient refused", transient,
                                   "transient" if transient else "invalid_recipient")
        except smtplib.SMTPResponseException as err:
            transient = 400 <= err.smtp_code < 500
            return EmailSendResult(False, "smtp", "SMTP request rejected", transient,
                                   "transient" if transient else "permanent")
        except (socket.timeout, smtplib.SMTPServerDisconnected, OSError):
            return EmailSendResult(False, "smtp", "SMTP transport outcome unknown", True, "transient")
        except smtplib.SMTPException:
            return EmailSendResult(False, "smtp", "SMTP permanent failure", False, "permanent")



def get_email_sender() -> EmailSender:
    """Financial notifications select their own adapter."""
    return _get_sender(settings.EMAIL_BACKEND)


def get_identity_email_sender() -> EmailSender:
    """Identity delivery never depends on the financial-notification backend."""
    return _get_sender(settings.SECURITY_EMAIL_BACKEND)


def _get_sender(backend: str) -> EmailSender:
    if settings.APP_ENV == "production" and backend != "smtp":
        raise ValueError("Production email requires SMTP")
    if backend == "smtp":
        return SmtpEmailSender(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_USE_TLS,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )
    if backend == "test":
        return TestEmailSender()
    raise ValueError("Unsupported email backend")
