"""Pieces the settings service, the request path and the worker share."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.settings import get_settings
from app.core.security.secret_box import SecretBoxError, open_sealed
from app.core.utils.dates import utc_now
from app.customers.models import Customer, CustomerContact
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentTypeDefinition,
)
from app.messaging.models import MessagingChannelConfig, MessagingOutbox
from app.messaging.providers import ADAPTERS, MessagingAdapter

logger = logging.getLogger("app.messaging")

HEALTH_NOT_CONFIGURED = "NOT_CONFIGURED"
HEALTH_UNTESTED = "UNTESTED"
HEALTH_OK = "OK"
HEALTH_NEEDS_ATTENTION = "NEEDS_ATTENTION"

QUEUED = "QUEUED"
SENDING = "SENDING"
SENT = "SENT"
DELIVERED = "DELIVERED"
READ = "READ"
FAILED = "FAILED"
SKIPPED = "SKIPPED"


def credential_key() -> str | None:
    """Return the key credentials are sealed under, or None if there is none."""
    return get_settings().messaging_secret()


@dataclass(frozen=True, slots=True)
class MessagingDocument:
    """What a message needs to know about the document it is about."""

    document_type: str
    document_id: UUID
    document_number: str
    document_date: date | None
    customer_id: UUID | None
    amount: Decimal | None = None
    due_date: date | None = None


def money(value: Decimal | None) -> str:
    """Render an amount the way a message prints it."""
    if value is None:
        return ""
    return f"{Decimal(value):,.2f}"


def day(value: date | None) -> str:
    """Render a date the way a message prints it: 04-Aug-2026."""
    return "" if value is None else value.strftime("%d-%b-%Y")


def adapter_for(config: MessagingChannelConfig) -> MessagingAdapter:
    """Build the provider adapter for a saved account, secrets opened.

    Raises:
        SecretBoxError: If the secrets cannot be opened with this server's key.
        KeyError: If the provider is not one this release knows.

    """
    adapter_class = ADAPTERS[config.provider]
    values: dict[str, str] = {
        str(key): str(value) for key, value in (config.public_settings or {}).items()
    }
    if config.credentials_encrypted:
        key = credential_key()
        if key is None:
            raise SecretBoxError(
                "This server has no AGENCY_MESSAGING_KEY, so the saved account "
                "cannot be opened."
            )
        secrets = json.loads(open_sealed(config.credentials_encrypted, secret=key))
        values.update({str(name): str(value) for name, value in secrets.items()})
    return adapter_class(values)


def channel_configs(
    session: Session, firm_id: UUID
) -> dict[str, MessagingChannelConfig]:
    """Return the firm's saved channel accounts, by channel."""
    rows = session.scalars(
        select(MessagingChannelConfig).where(
            MessagingChannelConfig.firm_id == firm_id,
            MessagingChannelConfig.is_deleted.is_(False),
        )
    ).all()
    return {row.channel: row for row in rows}


def is_usable(config: MessagingChannelConfig | None) -> str | None:
    """Return why a channel cannot send now, or None when it can."""
    if config is None or not config.provider:
        return "no account is set up"
    if not config.is_enabled:
        return "it is switched off"
    if config.health != HEALTH_OK:
        return (
            "it needs attention"
            if config.health == HEALTH_NEEDS_ATTENTION
            else ("it has not passed Test")
        )
    return None


def recipient_for(
    session: Session, customer: Customer | None, channel: str
) -> tuple[str | None, str | None]:
    """Return ``(address, why_not)`` for one customer on one channel.

    The customer's own email or phone first, then the primary contact's, then
    any contact's. WhatsApp also needs the customer's recorded opt-in: Meta's
    rules, and the decent thing.
    """
    if customer is None:
        return None, "the document names no customer"
    if channel == "WHATSAPP" and not customer.whatsapp_opt_in:
        return None, "the customer has not opted in to WhatsApp"
    contacts = sorted(
        (
            contact
            for contact in session.scalars(
                select(CustomerContact).where(
                    CustomerContact.customer_id == customer.id,
                    CustomerContact.is_deleted.is_(False),
                )
            ).all()
        ),
        key=lambda contact: (not contact.is_primary, contact.created_at),
    )
    if channel == "EMAIL":
        address = customer.email or next(
            (contact.email for contact in contacts if contact.email), None
        )
        return (address, None) if address else (None, "the customer has no email")
    number = customer.phone or next(
        (contact.mobile for contact in contacts if contact.mobile), None
    )
    return (number, None) if number else (None, "the customer has no phone number")


def record_on_timeline(session: Session, row: MessagingOutbox, action: str) -> None:
    """Put one send, failure or skip on its document's timeline.

    Only where the document's type is set up in the firm -- every module
    document is -- and never allowed to fail the caller.
    """
    if row.document_id is None or row.document_type is None:
        return
    type_id = session.scalar(
        select(DocumentTypeDefinition.id).where(
            DocumentTypeDefinition.firm_id == row.firm_id,
            DocumentTypeDefinition.code == row.document_type,
            DocumentTypeDefinition.is_deleted.is_(False),
        )
    )
    if type_id is None:
        return
    channel_label = {"EMAIL": "Email", "WHATSAPP": "WhatsApp", "SMS": "SMS"}.get(
        row.channel, row.channel
    )
    verb = {
        "MESSAGE_SENT": "sent",
        "MESSAGE_FAILED": "failed",
        "MESSAGE_SKIPPED": "skipped",
    }.get(action, action.lower())
    remark = f"{channel_label} {verb}"
    if row.recipient:
        remark += f" to {row.recipient}"
    if row.reason and action != "MESSAGE_SENT":
        remark += f": {row.reason}"
    session.add(
        DocumentLifecycleEvent(
            firm_id=row.firm_id,
            document_type_id=type_id,
            source_document_id=row.document_id,
            source_module_code=row.document_type,
            document_number=row.document_number,
            action=action,
            remarks=remark[:2000],
            details_json={
                "message_id": str(row.id),
                "event_code": row.event_code,
                "channel": row.channel,
                "status": row.status,
                "reason": row.reason,
                "is_resend": row.is_resend,
            },
            actor_id=row.requested_by,
            created_by=row.requested_by,
            updated_by=row.requested_by,
            email_recipient=(row.recipient if row.channel == "EMAIL" else None),
            occurred_at=utc_now(),
        )
    )
