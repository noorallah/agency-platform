"""The providers a firm may connect, keyed by what is stored on a channel.

One per channel today: SMTP for email, Meta's Cloud API for WhatsApp, MSG91 for
SMS (owner, 2026-10-01). A second provider for a channel is one more adapter
here; the settings page draws its form from ``required_fields`` and changes
not at all.
"""

from app.messaging.providers.base import (
    Attachment,
    MessagingAdapter,
    OutgoingMessage,
    ProviderError,
    ProviderField,
    SendResult,
    scrub,
)
from app.messaging.providers.sms_msg91 import Msg91Adapter
from app.messaging.providers.smtp import SmtpAdapter
from app.messaging.providers.whatsapp_meta import WhatsAppCloudAdapter

#: Every provider, by its stored key. Tests add a fake one here.
ADAPTERS: dict[str, type[MessagingAdapter]] = {
    SmtpAdapter.provider: SmtpAdapter,
    WhatsAppCloudAdapter.provider: WhatsAppCloudAdapter,
    Msg91Adapter.provider: Msg91Adapter,
}

#: The channels, in the order the page shows them.
CHANNELS: tuple[str, ...] = ("EMAIL", "WHATSAPP", "SMS")


def providers_for(channel: str) -> list[type[MessagingAdapter]]:
    """Return the providers that can serve a channel."""
    return [adapter for adapter in ADAPTERS.values() if adapter.channel == channel]


__all__ = [
    "ADAPTERS",
    "CHANNELS",
    "Attachment",
    "MessagingAdapter",
    "Msg91Adapter",
    "OutgoingMessage",
    "ProviderError",
    "ProviderField",
    "SendResult",
    "SmtpAdapter",
    "WhatsAppCloudAdapter",
    "providers_for",
    "scrub",
]
