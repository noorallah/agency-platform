"""Email through the firm's own mail account over SMTP.

Gmail and Outlook with an app password, or the firm's domain mail. The PDF is
attached rather than linked (§51, decision 3): nothing is served to the
internet, and the customer's accounts department files the attachment.

SMTP has no way to ask afterwards whether a message arrived, so a sent email
stays *sent* -- a bounce comes back to the firm's own mailbox.
"""

import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.messaging.providers.base import (
    MessagingAdapter,
    OutgoingMessage,
    ProviderError,
    ProviderField,
    SendResult,
    scrub,
)

#: Seconds to wait for the mail server.
TIMEOUT_SECONDS = 30


def _smtp_connect(host: str, port: int, security: str) -> smtplib.SMTP:
    """Open a connection: TLS from the start for SSL, plain for the rest."""
    if security == "SSL":
        return smtplib.SMTP_SSL(
            host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context()
        )
    return smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)


#: Builds the connection; replaced in tests so nothing reaches a network.
connect: Callable[[str, int, str], smtplib.SMTP] = _smtp_connect


class SmtpAdapter(MessagingAdapter):
    """Send email through an SMTP server."""

    provider = "SMTP"
    channel = "EMAIL"
    label = "Email (SMTP)"

    @classmethod
    def required_fields(cls) -> tuple[ProviderField, ...]:
        """Return the fields an SMTP account needs."""
        return (
            ProviderField(
                "host",
                "SMTP server",
                help="smtp.gmail.com, smtp.office365.com, or your mail host.",
            ),
            ProviderField("port", "Port", kind="number", default="587"),
            ProviderField(
                "security",
                "Security",
                kind="choice",
                choices=("STARTTLS", "SSL", "NONE"),
                default="STARTTLS",
                help="587 uses STARTTLS, 465 uses SSL.",
            ),
            ProviderField("username", "User name", help="Usually the address."),
            ProviderField(
                "password",
                "Password",
                secret=True,
                kind="password",
                help="Gmail and Outlook need an app password, not your own.",
            ),
            ProviderField("from_email", "Send from", kind="email"),
            ProviderField("from_name", "Sender name", required=False),
        )

    def _open(self) -> smtplib.SMTP:
        """Connect, secure and sign in."""
        host = self.setting("host")
        security = (self.setting("security") or "STARTTLS").upper()
        try:
            port = int(self.setting("port") or "587")
        except ValueError as error:
            raise ProviderError("The port must be a number.", permanent=True) from error
        try:
            server = connect(host, port, security)
            if security == "STARTTLS":
                server.starttls(context=ssl.create_default_context())
            if self.setting("username"):
                server.login(self.setting("username"), self.setting("password"))
        except smtplib.SMTPAuthenticationError as error:
            raise ProviderError(
                "The mail server refused the user name or password. Gmail and "
                "Outlook need an app password.",
                permanent=True,
            ) from error
        except (smtplib.SMTPException, OSError) as error:
            raise ProviderError(
                scrub(
                    f"Could not reach the mail server: {error}", self.secret_values()
                ),
                permanent=False,
            ) from error
        return server

    def test_connection(self) -> None:
        """Connect and sign in, then leave."""
        server = self._open()
        try:
            server.noop()
        finally:
            _quit(server)

    def send(self, message: OutgoingMessage) -> SendResult:
        """Send one email, with its attachments."""
        email = EmailMessage()
        sender = self.setting("from_email")
        email["From"] = formataddr((self.setting("from_name") or "", sender))
        email["To"] = message.to
        email["Subject"] = message.subject or ""
        message_id = make_msgid(domain=sender.split("@")[-1] or None)
        email["Message-ID"] = message_id
        email.set_content(message.body or "")
        for attachment in message.attachments:
            main, _, sub = attachment.mime_type.partition("/")
            email.add_attachment(
                attachment.content,
                maintype=main,
                subtype=sub or "octet-stream",
                filename=attachment.filename,
            )
        server = self._open()
        try:
            refused = server.send_message(email)
        except smtplib.SMTPRecipientsRefused as error:
            raise ProviderError(
                f"The mail server refused the address {message.to}.", permanent=True
            ) from error
        except (smtplib.SMTPException, OSError) as error:
            raise ProviderError(
                scrub(f"Sending failed: {error}", self.secret_values()),
                permanent=False,
            ) from error
        finally:
            _quit(server)
        if refused:
            raise ProviderError(
                f"The mail server refused the address {message.to}.", permanent=True
            )
        return SendResult(provider_message_id=message_id)


def _quit(server: smtplib.SMTP) -> None:
    """Close the connection, ignoring a server that already hung up."""
    try:
        server.quit()
    except (smtplib.SMTPException, OSError):
        server.close()
