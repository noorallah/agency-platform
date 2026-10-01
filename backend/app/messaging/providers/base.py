"""The one interface every messaging provider is reached through.

``required_fields()`` is what the settings page draws its form from, so adding
a provider changes no screen. ``send``, ``fetch_status`` and
``test_connection`` are everything the outbox worker and the Test button need.

**No webhooks.** The server sits inside the office and a provider cannot call
in, so status is fetched by the worker on a timer -- where the provider offers
a way to fetch it. Where it does not, ``fetch_status`` answers ``None`` and the
message stays *sent*; it is never shown as *delivered* on a guess.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ProviderField:
    """One field of a provider account, as the settings form shows it."""

    name: str
    label: str
    #: Secret fields are sealed at rest and never returned; the page offers
    #: only *Replace*.
    secret: bool = False
    required: bool = True
    #: ``text``, ``number``, ``password``, ``email`` or ``choice``.
    kind: str = "text"
    help: str | None = None
    choices: tuple[str, ...] = ()
    default: str | None = None


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file sent with an email."""

    filename: str
    content: bytes
    mime_type: str = "application/pdf"


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    """Everything one send needs, already rendered."""

    to: str
    subject: str | None = None
    body: str | None = None
    template_name: str | None = None
    template_language: str | None = None
    variables: tuple[str, ...] = ()
    attachments: tuple[Attachment, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SendResult:
    """What the provider said when it took the message."""

    provider_message_id: str | None


class ProviderError(Exception):
    """A provider refused or could not be reached.

    ``permanent`` decides what the worker does next: a permanent refusal
    (bad credentials, a template the provider does not know, a number it
    will not message) marks the channel *needs attention* and falls to the
    next channel at once; a transient one (a timeout, a 5xx, a rate limit) is
    retried with back-off first.
    """

    def __init__(self, message: str, *, permanent: bool) -> None:
        """Keep the message and whether retrying could help."""
        super().__init__(message)
        self.message = message
        self.permanent = permanent


def scrub(message: str, secrets: Mapping[str, str]) -> str:
    """Remove every secret value from a message before it is stored or logged.

    A provider's error text is shown on the page and kept on the outbox row.
    None of the three providers echoes a credential today; this makes sure a
    future one, or a URL in an exception, cannot put one there.
    """
    cleaned = message
    for value in secrets.values():
        if value and len(value) >= 4:
            cleaned = cleaned.replace(value, "<redacted>")
    return cleaned[:1000]


class MessagingAdapter(ABC):
    """One provider, bound to one firm's account with it."""

    #: The registry key, stored on the channel config.
    provider: ClassVar[str]
    #: EMAIL, WHATSAPP or SMS.
    channel: ClassVar[str]
    #: What the settings page calls it.
    label: ClassVar[str]
    #: Whether this provider can be asked for a message's status.
    supports_status: ClassVar[bool] = False

    def __init__(self, settings: Mapping[str, str]) -> None:
        """Bind to the account: public and secret fields together."""
        self._settings = dict(settings)

    @classmethod
    @abstractmethod
    def required_fields(cls) -> tuple[ProviderField, ...]:
        """Return the fields an account with this provider needs."""

    @abstractmethod
    def send(self, message: OutgoingMessage) -> SendResult:
        """Hand one message to the provider.

        Raises:
            ProviderError: If the provider refused it or could not be reached.

        """

    def fetch_status(self, provider_message_id: str) -> str | None:
        """Return DELIVERED, READ or FAILED, or None when it cannot say."""
        return None

    @abstractmethod
    def test_connection(self) -> None:
        """Prove the account works, without sending anybody anything.

        Raises:
            ProviderError: With the provider's own reason.

        """

    def secret_values(self) -> dict[str, str]:
        """Return the secret fields' values, for :func:`scrub`."""
        names = {field.name for field in self.required_fields() if field.secret}
        return {name: self._settings.get(name, "") for name in names}

    def setting(self, name: str) -> str:
        """Return one account field, or an empty string."""
        return str(self._settings.get(name) or "").strip()
