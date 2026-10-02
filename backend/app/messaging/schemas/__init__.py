"""Request and response models for messaging (BACKLOG 51).

No response model has a field a credential could travel in: a channel reports
its public settings and the **names** of the secrets it holds, never a value.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MessagingChannel = Literal["EMAIL", "WHATSAPP", "SMS"]
ChannelHealth = Literal["NOT_CONFIGURED", "UNTESTED", "OK", "NEEDS_ATTENTION"]
MessageStatus = Literal[
    "QUEUED", "SENDING", "SENT", "DELIVERED", "READ", "FAILED", "SKIPPED"
]


class MessagingSchema(BaseModel):
    """Strict input and ORM-friendly output."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ProviderFieldResponse(MessagingSchema):
    """One field of a provider account, for the settings form."""

    name: str
    label: str
    secret: bool
    required: bool
    kind: str
    help: str | None = None
    choices: list[str] = Field(default_factory=list)
    default: str | None = None


class ProviderResponse(MessagingSchema):
    """A provider a channel can be connected through."""

    provider: str
    channel: MessagingChannel
    label: str
    supports_status: bool
    fields: list[ProviderFieldResponse]


class MessagingEventResponse(MessagingSchema):
    """An event a firm may send on, and what its templates may use."""

    code: str
    label: str
    document_type: str
    #: In order: WhatsApp {{1}}.. and MSG91 var1.. are filled from these.
    variables: list[str]
    is_reminder: bool
    attaches_pdf: bool
    default_subject: str
    default_body: str


class MessagingSettingsResponse(MessagingSchema):
    """The firm's master switch and reminder schedule."""

    is_enabled: bool
    due_soon_days: int
    overdue_every_days: int
    #: A bill more than this many days overdue is not reminded (A12).
    overdue_stop_after_days: int
    #: False until the firm saves the page once.
    is_configured: bool
    #: False when the server has no AGENCY_MESSAGING_KEY in production: no
    #: provider account can be saved until the operator sets one.
    can_store_credentials: bool


class MessagingSettingsWrite(MessagingSchema):
    """Change the master switch or the schedule. Absent fields stay as they are."""

    is_enabled: bool = False
    due_soon_days: int = Field(default=3, ge=0, le=60)
    overdue_every_days: int = Field(default=7, ge=1, le=90)
    overdue_stop_after_days: int = Field(default=90, ge=1, le=3650)


class ChannelResponse(MessagingSchema):
    """One channel: which provider, whether it works, whether it is on."""

    channel: MessagingChannel
    provider: str | None
    is_enabled: bool
    health: ChannelHealth
    is_configured: bool
    #: The provider's non-secret fields, as saved.
    settings: dict[str, str]
    #: The names of the secret fields that hold a value. Never the values.
    secrets_set: list[str]
    last_tested_at: datetime | None
    last_error: str | None


class ChannelAccountWrite(MessagingSchema):
    """Save (or replace) the account a channel sends through.

    A secret field left out, or blank, keeps the value already saved -- so a
    changed host does not mean retyping the password. Saving always clears a
    passed Test: the channel has to be tested again before it can be on.
    """

    provider: str = Field(min_length=1, max_length=30)
    settings: dict[str, str] = Field(default_factory=dict, max_length=20)


class EventChannelWrite(MessagingSchema):
    """One channel of an event's fallback chain."""

    channel: MessagingChannel
    is_enabled: bool = True
    template_name: str | None = Field(default=None, max_length=120)
    template_language: str | None = Field(default=None, max_length=10)
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=4000)


class EventChannelResponse(EventChannelWrite):
    """One channel of an event, as saved, with its place in the chain."""

    priority: int


class EventConfigWrite(MessagingSchema):
    """Replace an event's channels; their order is the fallback order."""

    channels: list[EventChannelWrite] = Field(default_factory=list, max_length=3)


class EventConfigResponse(MessagingSchema):
    """One event and the channels it goes out on."""

    event_code: str
    label: str
    is_enabled: bool
    channels: list[EventChannelResponse]


class MessageResponse(MessagingSchema):
    """One message in the log."""

    id: UUID
    event_code: str
    document_type: str | None
    document_id: UUID | None
    document_number: str | None
    customer_id: UUID | None
    channel: str
    provider: str | None
    recipient: str | None
    status: str
    reason: str | None
    subject: str | None
    template_name: str | None
    attempts: int
    is_resend: bool
    previous_message_id: UUID | None
    provider_message_id: str | None
    requested_by: UUID | None
    created_at: datetime
    next_attempt_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None


class ManualSendRequest(MessagingSchema):
    """Send one document by hand, now, on one channel."""

    document_type: Literal["SALES_INVOICE"] = "SALES_INVOICE"
    document_id: UUID
    channel: MessagingChannel
    #: Blank sends to the customer's own address or number.
    recipient: str | None = Field(default=None, max_length=320)
    #: Replaces the email body; WhatsApp and SMS send their template.
    message: str | None = Field(default=None, max_length=4000)


SharedDocument = Literal["SALES_INVOICE", "CUSTOMER_STATEMENT"]


class ReminderRequest(MessagingSchema):
    """Email a customer their statement as a payment reminder (MSG-3)."""

    customer_id: UUID
    #: Blank sends to the customer's own address.
    recipient: str | None = Field(default=None, max_length=320)
    #: Replaces the covering note.
    message: str | None = Field(default=None, max_length=4000)


class HandShareResponse(MessagingSchema):
    """What to share a document with by hand, from the person's own WhatsApp.

    No account and no API (MSG-1, §51 A2): the desktop opens WhatsApp at the
    number with the message typed in, and saves the PDF for the person to
    attach.
    """

    #: An invoice (MSG-1), or a customer's statement for a reminder (MSG-3),
    #: whose ``document_id`` is then the customer's.
    document_type: SharedDocument = "SALES_INVOICE"
    document_id: UUID
    document_number: str
    #: The number as the customer record holds it, for the screen.
    phone: str | None
    #: Digits only with the country code, as ``wa.me`` wants it; None where
    #: the customer has no number, and WhatsApp asks whom to send to.
    whatsapp_number: str | None
    text: str
    #: What to call the saved PDF.
    file_name: str


class HandShareRecord(MessagingSchema):
    """A share a person made by hand, for the document's timeline (A5)."""

    document_type: SharedDocument = "SALES_INVOICE"
    document_id: UUID
    channel: Literal["WHATSAPP"] = "WHATSAPP"
    recipient: str | None = Field(default=None, max_length=40)


__all__ = [
    "ChannelAccountWrite",
    "ChannelHealth",
    "ChannelResponse",
    "EventChannelResponse",
    "EventChannelWrite",
    "EventConfigResponse",
    "EventConfigWrite",
    "HandShareRecord",
    "HandShareResponse",
    "ManualSendRequest",
    "ReminderRequest",
    "SharedDocument",
    "MessageResponse",
    "MessageStatus",
    "MessagingChannel",
    "MessagingEventResponse",
    "MessagingSchema",
    "MessagingSettingsResponse",
    "MessagingSettingsWrite",
    "ProviderFieldResponse",
    "ProviderResponse",
]
