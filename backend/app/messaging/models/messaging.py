"""What a firm configured for messaging, and every message it asked for.

BACKLOG §51, built 2026-10-01 to the owner's decisions recorded in
``docs/MESSAGING_FRAMEWORK.md``: a feature each firm switches on for itself,
with its own provider accounts, on its own Messaging settings page. Every table
is firm-owned and lives in the firm's own store; none carries a foreign key to
``firms``, which exists only in the platform schema.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, Date, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UTCDateTime, UUIDType


class MessagingSettings(BaseEntity):
    """One firm's master switch and reminder schedule.

    A firm with no row has messaging **off**: nothing is queued, skipped or
    recorded for it, and every document behaves exactly as before.
    """

    __tablename__ = "messaging_settings"
    __table_args__ = (
        Index(
            "UQ_messaging_settings_firm_active",
            "firm_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: PAYMENT_DUE_SOON is sent this many days before a bill falls due.
    due_soon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    #: PAYMENT_OVERDUE is sent the day after a bill falls due and again every
    #: this many days while it is still owed.
    overdue_every_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default="7"
    )
    #: The UTC day the reminder scan last ran for this firm; it runs once a day.
    last_reminder_scan_on: Mapped[date | None] = mapped_column(Date)


class MessagingChannelConfig(BaseEntity):
    """One firm's account with one provider, for one channel.

    The provider's non-secret fields (an SMTP host, a WhatsApp phone number
    id, an SMS sender id) are kept readable in ``public_settings`` so the page
    can show them; the secret ones are sealed together in
    ``credentials_encrypted`` under ``AGENCY_MESSAGING_KEY`` and are never
    returned by any endpoint.
    """

    __tablename__ = "messaging_channel_configs"
    __table_args__ = (
        Index(
            "UQ_messaging_channel_configs_firm_channel_active",
            "firm_id",
            "channel",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: EMAIL, WHATSAPP or SMS.
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    #: SMTP, META_CLOUD or MSG91 -- a key of the adapter registry.
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    public_settings: Mapped[dict[str, object] | None] = mapped_column(JSON)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    #: NOT_CONFIGURED, UNTESTED, OK or NEEDS_ATTENTION. Only OK may be enabled.
    health: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NOT_CONFIGURED",
        server_default="NOT_CONFIGURED",
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class MessagingEventConfig(BaseEntity):
    """Whether one event goes out on one channel, and with which template.

    The rows of one event, ordered by ``priority``, are its fallback chain: a
    message goes on the first usable channel, and falls to the next when that
    one fails.
    """

    __tablename__ = "messaging_event_configs"
    __table_args__ = (
        Index(
            "UQ_messaging_event_configs_firm_event_channel_active",
            "firm_id",
            "event_code",
            "channel",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    event_code: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    #: The provider's template: a Meta-approved template name for WhatsApp, a
    #: MSG91 template id (registered on DLT) for SMS. Unused for email.
    template_name: Mapped[str | None] = mapped_column(String(120))
    #: The WhatsApp template's language code, for example `en` or `hi`.
    template_language: Mapped[str | None] = mapped_column(String(10))
    #: Email subject and body, with `{placeholders}`; blank takes the default.
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)


class MessagingOutbox(BaseEntity):
    """One message: asked for, queued, sent, failed or skipped.

    Written in the document's own transaction, so a document that rolls back
    leaves no message behind; sent later by the worker, so a provider that is
    slow or down never holds a document up.
    """

    __tablename__ = "messaging_outbox"
    __table_args__ = (
        # One message per (event, document, channel, occurrence) -- the
        # idempotency the owner asked for. A resend carries no key, which is
        # what makes it the only way to send twice.
        Index(
            "UQ_messaging_outbox_firm_dedupe_active",
            "firm_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND NOT is_deleted"),
            sqlite_where=text("dedupe_key IS NOT NULL AND NOT is_deleted"),
        ),
        Index("IX_messaging_outbox_firm_status_due", "firm_id", "status"),
        Index("IX_messaging_outbox_document", "firm_id", "document_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    event_code: Mapped[str] = mapped_column(String(40), nullable=False)
    #: The module code of the document: SALES_INVOICE, RECEIPT, ...
    document_type: Mapped[str | None] = mapped_column(String(40))
    document_id: Mapped[UUID | None] = mapped_column(UUIDType())
    document_number: Mapped[str | None] = mapped_column(String(80))
    customer_id: Mapped[UUID | None] = mapped_column(UUIDType())
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(30))
    recipient: Mapped[str | None] = mapped_column(String(320))
    #: QUEUED, SENDING, SENT, DELIVERED, READ, FAILED or SKIPPED.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Why it was skipped, or why the last attempt failed.
    reason: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    template_name: Mapped[str | None] = mapped_column(String(120))
    template_language: Mapped[str | None] = mapped_column(String(10))
    #: The template's variables, in order -- WhatsApp's {{1}}..{{n}}, MSG91's
    #: VAR1..VARn.
    variables: Mapped[list[str] | None] = mapped_column(JSON)
    attach_pdf: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: The channels still to try, in order, if this one fails.
    fallback_channels: Mapped[list[str] | None] = mapped_column(JSON)
    #: Reminder cycle or due date, so a reminder goes once per cycle.
    occurrence: Mapped[str | None] = mapped_column(String(40))
    dedupe_key: Mapped[str | None] = mapped_column(String(300))
    is_resend: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: The message this one resends, or falls back from.
    previous_message_id: Mapped[UUID | None] = mapped_column(UUIDType())
    requested_by: Mapped[UUID | None] = mapped_column(UUIDType())
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
