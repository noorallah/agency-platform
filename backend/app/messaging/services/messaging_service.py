"""A firm's messaging settings, and asking for a message.

**Off changes nothing.** A firm without messaging switched on gets no row of
any kind from :meth:`MessagingService.stage_event`: no queued message, no
skipped one, nothing on a timeline. A document's own behaviour never depends on
this module -- the staging call sits in a savepoint and swallows its own
failures, so a missing table or a bug here can neither block nor undo the
document it was asked about.

**In the document's transaction.** ``stage_event`` adds the outbox row to the
session the document is being written on and never commits. A document that
rolls back takes its message with it; one that commits has its message queued,
and the worker sends it after.
"""

import json
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.secret_box import SecretBoxError, open_sealed, seal
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.messaging.events import EVENTS, EVENTS_BY_CODE, MANUAL_SEND, render
from app.messaging.models import (
    MessagingChannelConfig,
    MessagingEventConfig,
    MessagingOutbox,
    MessagingSettings,
)
from app.messaging.providers import ADAPTERS, CHANNELS, ProviderError
from app.messaging.schemas import (
    ChannelAccountWrite,
    ChannelResponse,
    EventChannelResponse,
    EventConfigResponse,
    EventConfigWrite,
    ManualSendRequest,
    MessagingSettingsResponse,
    MessagingSettingsWrite,
)
from app.messaging.services.common import (
    HEALTH_NEEDS_ATTENTION,
    HEALTH_NOT_CONFIGURED,
    HEALTH_OK,
    HEALTH_UNTESTED,
    QUEUED,
    SKIPPED,
    MessagingDocument,
    adapter_for,
    channel_configs,
    credential_key,
    day,
    is_usable,
    logger,
    money,
    recipient_for,
    record_on_timeline,
)
from app.sales_invoice.models import SalesInvoice


def dedupe_key(
    event_code: str, document_id: UUID | None, channel: str, occurrence: str | None
) -> str:
    """Return the key that makes a message once-only."""
    return f"{event_code}|{document_id}|{channel}|{occurrence or ''}"


class MessagingService:
    """Settings, the message log, and staging a message for a document."""

    def __init__(self, session: Session) -> None:
        """Hold the firm-store session."""
        self._session = session

    # -- Master switch and schedule ----------------------------------------

    def _settings_row(self, firm_id: UUID) -> MessagingSettings | None:
        """Return the firm's settings row, if it ever saved one."""
        return self._session.scalar(
            select(MessagingSettings).where(
                MessagingSettings.firm_id == firm_id,
                MessagingSettings.is_deleted.is_(False),
            )
        )

    def settings_response(self, firm_id: UUID) -> MessagingSettingsResponse:
        """Report the master switch, the schedule, and whether keys can be kept."""
        row = self._settings_row(firm_id)
        return MessagingSettingsResponse(
            is_enabled=bool(row and row.is_enabled),
            due_soon_days=row.due_soon_days if row else 3,
            overdue_every_days=row.overdue_every_days if row else 7,
            is_configured=row is not None,
            can_store_credentials=credential_key() is not None,
        )

    def update_settings(
        self, data: MessagingSettingsWrite, *, firm_id: UUID, actor_id: UUID
    ) -> MessagingSettingsResponse:
        """Change the master switch or the schedule; absent fields stay."""
        row = self._settings_row(firm_id)
        before: dict[str, object] | None = None
        if row is None:
            row = MessagingSettings(firm_id=firm_id, created_by=actor_id)
            self._session.add(row)
            values = data.model_dump()
        else:
            before = _settings_snapshot(row)
            values = data.model_dump(exclude_unset=True)
        for name, value in values.items():
            setattr(row, name, value)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "messaging_settings.updated"
                if before is not None
                else "messaging_settings.created"
            ),
            entity_type="messaging_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=_settings_snapshot(row),
        )
        self._session.commit()
        return self.settings_response(firm_id)

    # -- Channels -----------------------------------------------------------

    def channels(self, firm_id: UUID) -> list[ChannelResponse]:
        """Report every channel, configured or not."""
        saved = channel_configs(self._session, firm_id)
        return [
            self._channel_response(channel, saved.get(channel)) for channel in CHANNELS
        ]

    def channel(self, channel: str, firm_id: UUID) -> ChannelResponse:
        """Report one channel."""
        return self._channel_response(
            channel, channel_configs(self._session, firm_id).get(channel)
        )

    @staticmethod
    def _channel_response(
        channel: str, row: MessagingChannelConfig | None
    ) -> ChannelResponse:
        """Describe a channel without a single secret value in it."""
        if row is None:
            return ChannelResponse(
                channel=channel,
                provider=None,
                is_enabled=False,
                health=HEALTH_NOT_CONFIGURED,
                is_configured=False,
                settings={},
                secrets_set=[],
                last_tested_at=None,
                last_error=None,
            )
        adapter = ADAPTERS.get(row.provider)
        secret_names = (
            [field.name for field in adapter.required_fields() if field.secret]
            if adapter is not None
            else []
        )
        return ChannelResponse(
            channel=row.channel,
            provider=row.provider,
            is_enabled=row.is_enabled,
            health=row.health,
            is_configured=row.health != HEALTH_NOT_CONFIGURED,
            settings={
                str(key): str(value)
                for key, value in (row.public_settings or {}).items()
            },
            secrets_set=secret_names if row.credentials_encrypted else [],
            last_tested_at=row.last_tested_at,
            last_error=row.last_error,
        )

    def save_account(
        self,
        channel: str,
        data: ChannelAccountWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> ChannelResponse:
        """Save or replace the account a channel sends through.

        The channel goes off and back to *untested*: a changed account has not
        been shown to work, and only a passed Test lets it on again.
        """
        _known_channel(channel)
        adapter_class = ADAPTERS.get(data.provider)
        if adapter_class is None or adapter_class.channel != channel:
            raise ValidationError(f"{data.provider} cannot send {channel.lower()}.")
        key = credential_key()
        if key is None:
            raise ValidationError(
                "This server cannot store provider accounts yet: its operator "
                "has to set AGENCY_MESSAGING_KEY in config\\.env and restart it."
            )
        fields = {field.name: field for field in adapter_class.required_fields()}
        unknown = sorted(set(data.settings) - set(fields))
        if unknown:
            raise ValidationError(
                f"{adapter_class.label} has no field {', '.join(unknown)}."
            )
        row = channel_configs(self._session, firm_id).get(channel)
        stored_secrets: dict[str, str] = {}
        if (
            row is not None
            and row.provider == data.provider
            and row.credentials_encrypted
        ):
            try:
                stored_secrets = json.loads(
                    open_sealed(row.credentials_encrypted, secret=key)
                )
            except SecretBoxError:
                # Saved under another key: the old secrets are unreadable, so
                # the form has to supply them all again.
                stored_secrets = {}
        public: dict[str, object] = {}
        secrets: dict[str, str] = {}
        missing: list[str] = []
        for name, field in fields.items():
            sent = (data.settings.get(name) or "").strip()
            if field.secret:
                value = sent or str(stored_secrets.get(name) or "")
                if value:
                    secrets[name] = value
            else:
                value = sent or (field.default or "")
                if value:
                    public[name] = value
            if field.required and not value:
                missing.append(field.label)
        if missing:
            raise ValidationError(f"Enter {', '.join(missing)}.")
        created = row is None
        if row is None:
            row = MessagingChannelConfig(
                firm_id=firm_id, channel=channel, created_by=actor_id
            )
            self._session.add(row)
        row.provider = data.provider
        row.public_settings = public
        row.credentials_encrypted = (
            seal(json.dumps(secrets), secret=key) if secrets else None
        )
        row.health = HEALTH_UNTESTED
        row.is_enabled = False
        row.last_error = None
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "messaging_channel.created" if created else "messaging_channel.replaced"
            ),
            entity_type="messaging_channel_config",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            # Which fields were saved, never a value of a secret one.
            after_data={
                "channel": channel,
                "provider": data.provider,
                "settings": public,
                "secrets_set": sorted(secrets),
            },
        )
        self._session.commit()
        return self._channel_response(channel, row)

    def test_channel(
        self, channel: str, *, firm_id: UUID, actor_id: UUID
    ) -> ChannelResponse:
        """Prove the saved account works; record OK or *needs attention*."""
        row = self._require_channel(channel, firm_id)
        error: str | None = None
        try:
            adapter_for(row).test_connection()
        except ProviderError as failure:
            error = failure.message
        except (SecretBoxError, KeyError, ValueError) as failure:
            error = str(failure)
        row.last_tested_at = utc_now()
        row.health = HEALTH_OK if error is None else HEALTH_NEEDS_ATTENTION
        row.last_error = error
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="messaging_channel.tested",
            entity_type="messaging_channel_config",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"channel": channel, "health": row.health, "error": error},
        )
        self._session.commit()
        return self._channel_response(channel, row)

    def set_channel_enabled(
        self, channel: str, enabled: bool, *, firm_id: UUID, actor_id: UUID
    ) -> ChannelResponse:
        """Switch a channel on -- only after a passed Test -- or off."""
        row = self._require_channel(channel, firm_id)
        if enabled and row.health != HEALTH_OK:
            raise ValidationError(
                "Test the account first: a channel can be switched on only "
                "after its Test has passed."
            )
        before = row.is_enabled
        row.is_enabled = enabled
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action=(
                "messaging_channel.enabled" if enabled else "messaging_channel.disabled"
            ),
            entity_type="messaging_channel_config",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"is_enabled": before},
            after_data={"channel": channel, "is_enabled": enabled},
        )
        self._session.commit()
        return self._channel_response(channel, row)

    def _require_channel(self, channel: str, firm_id: UUID) -> MessagingChannelConfig:
        """Return a channel's saved account, or say there is none."""
        _known_channel(channel)
        row = channel_configs(self._session, firm_id).get(channel)
        if row is None:
            raise ResourceNotFoundError(
                f"No {channel.lower()} account is saved for this firm yet."
            )
        return row

    # -- Events -------------------------------------------------------------

    def _event_rows(self, firm_id: UUID) -> list[MessagingEventConfig]:
        """Return every saved event channel, in fallback order."""
        return list(
            self._session.scalars(
                select(MessagingEventConfig)
                .where(
                    MessagingEventConfig.firm_id == firm_id,
                    MessagingEventConfig.is_deleted.is_(False),
                )
                .order_by(
                    MessagingEventConfig.event_code,
                    MessagingEventConfig.priority,
                    MessagingEventConfig.channel,
                )
            ).all()
        )

    def event_configs(self, firm_id: UUID) -> list[EventConfigResponse]:
        """Report every event the firm may choose, with its channels."""
        by_event: dict[str, list[MessagingEventConfig]] = {}
        for row in self._event_rows(firm_id):
            by_event.setdefault(row.event_code, []).append(row)
        return [
            _event_response(event.code, event.label, by_event.get(event.code, []))
            for event in EVENTS
        ]

    def save_event_config(
        self,
        event_code: str,
        data: EventConfigWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> EventConfigResponse:
        """Replace one event's channels; their order is the fallback order."""
        event = EVENTS_BY_CODE.get(event_code)
        if event is None:
            raise ResourceNotFoundError(f"There is no messaging event {event_code}.")
        channels = [item.channel for item in data.channels]
        if len(set(channels)) != len(channels):
            raise ValidationError("Name each channel once.")
        existing = {
            row.channel: row
            for row in self._event_rows(firm_id)
            if row.event_code == event_code
        }
        before = [_event_row_snapshot(row) for row in existing.values()]
        for channel, row in existing.items():
            if channel not in channels:
                row.is_deleted = True
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
        # Clear the soft-deleted rows before any insert reuses their key.
        self._session.flush()
        kept: list[MessagingEventConfig] = []
        for priority, item in enumerate(data.channels, start=1):
            entry = existing.get(item.channel)
            if entry is None:
                entry = MessagingEventConfig(
                    firm_id=firm_id,
                    event_code=event_code,
                    channel=item.channel,
                    created_by=actor_id,
                )
                self._session.add(entry)
            entry.is_enabled = item.is_enabled
            entry.priority = priority
            entry.template_name = (item.template_name or "").strip() or None
            entry.template_language = (item.template_language or "").strip() or None
            entry.subject = (item.subject or "").strip() or None
            entry.body = (item.body or "").strip() or None
            entry.updated_by = actor_id
            kept.append(entry)
        self._session.flush()
        record_audit(
            self._session,
            action="messaging_event.updated",
            entity_type="messaging_event_config",
            entity_id=kept[0].id if kept else firm_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"event_code": event_code, "channels": before},
            after_data={
                "event_code": event_code,
                "channels": [_event_row_snapshot(row) for row in kept],
            },
        )
        self._session.commit()
        return _event_response(event.code, event.label, kept)

    # -- The log ------------------------------------------------------------

    def list_messages(
        self,
        firm_id: UUID,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        channel: str | None = None,
        event_code: str | None = None,
        document_id: UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[MessagingOutbox], int]:
        """Return one page of the firm's messages, newest first."""
        conditions = [
            MessagingOutbox.firm_id == firm_id,
            MessagingOutbox.is_deleted.is_(False),
        ]
        if status:
            conditions.append(MessagingOutbox.status == status)
        if channel:
            conditions.append(MessagingOutbox.channel == channel)
        if event_code:
            conditions.append(MessagingOutbox.event_code == event_code)
        if document_id:
            conditions.append(MessagingOutbox.document_id == document_id)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                MessagingOutbox.document_number.ilike(pattern)
                | MessagingOutbox.recipient.ilike(pattern)
            )
        total = int(
            self._session.scalar(
                select(func.count()).select_from(MessagingOutbox).where(*conditions)
            )
            or 0
        )
        rows = self._session.scalars(
            select(MessagingOutbox)
            .where(*conditions)
            .order_by(MessagingOutbox.created_at.desc(), MessagingOutbox.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total

    # -- Asking for a message ------------------------------------------------

    def stage_event(
        self,
        event_code: str,
        document: MessagingDocument,
        *,
        firm_id: UUID,
        actor_id: UUID | None,
        occurrence: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> MessagingOutbox | None:
        """Ask for one event's message, in the caller's transaction.

        Never raises and never commits. Returns the row staged -- queued or
        skipped -- or None when the firm has not asked for this message at all.
        """
        # The document's own pending work is flushed here, outside the guard:
        # `begin_nested` would flush it anyway, and a failure in *that* is the
        # document's to report, never this module's to swallow.
        self._session.flush()
        try:
            with self._session.begin_nested():
                return self._stage_event(
                    event_code,
                    document,
                    firm_id=firm_id,
                    actor_id=actor_id,
                    occurrence=occurrence,
                    extra=variables or {},
                )
        except Exception:  # noqa: BLE001 - a message must never fail a document
            logger.exception(
                "messaging.stage_event failed: event=%s document=%s",
                event_code,
                document.document_number,
            )
            return None

    def _stage_event(
        self,
        event_code: str,
        document: MessagingDocument,
        *,
        firm_id: UUID,
        actor_id: UUID | None,
        occurrence: str | None,
        extra: dict[str, str],
    ) -> MessagingOutbox | None:
        """Do the work of :meth:`stage_event`, which guards it."""
        settings = self._settings_row(firm_id)
        if settings is None or not settings.is_enabled:
            return None
        chain = [
            row
            for row in self._event_rows(firm_id)
            if row.event_code == event_code and row.is_enabled
        ]
        if not chain:
            return None
        already = self._session.scalar(
            select(MessagingOutbox.id).where(
                MessagingOutbox.firm_id == firm_id,
                MessagingOutbox.event_code == event_code,
                MessagingOutbox.document_id == document.document_id,
                MessagingOutbox.is_resend.is_(False),
                MessagingOutbox.previous_message_id.is_(None),
                (
                    MessagingOutbox.occurrence.is_(None)
                    if occurrence is None
                    else MessagingOutbox.occurrence == occurrence
                ),
                MessagingOutbox.is_deleted.is_(False),
            )
        )
        if already is not None:
            return None
        event = EVENTS_BY_CODE[event_code]
        customer = (
            None
            if document.customer_id is None
            else self._session.get(Customer, document.customer_id)
        )
        values = self._variables(document, customer, firm_id) | extra
        ordered = _preferred_first(chain, customer)
        if event.is_reminder and customer is not None and customer.no_reminders:
            return self._stage_row(
                firm_id=firm_id,
                event_code=event_code,
                document=document,
                config=ordered[0],
                values=values,
                status=SKIPPED,
                reason="The customer asked for no reminders.",
                recipient=None,
                fallback=[],
                occurrence=occurrence,
                actor_id=actor_id,
                attach=False,
            )
        accounts = channel_configs(self._session, firm_id)
        reasons: list[str] = []
        for index, config in enumerate(ordered):
            why_not = is_usable(accounts.get(config.channel))
            recipient: str | None = None
            if why_not is None:
                recipient, why_not = recipient_for(
                    self._session, customer, config.channel
                )
            if why_not is not None:
                reasons.append(f"{_label(config.channel)}: {why_not}")
                continue
            return self._stage_row(
                firm_id=firm_id,
                event_code=event_code,
                document=document,
                config=config,
                values=values,
                status=QUEUED,
                reason=None,
                recipient=recipient,
                fallback=[row.channel for row in ordered[index + 1 :]],
                occurrence=occurrence,
                actor_id=actor_id,
                attach=event.attaches_pdf,
            )
        return self._stage_row(
            firm_id=firm_id,
            event_code=event_code,
            document=document,
            config=ordered[0],
            values=values,
            status=SKIPPED,
            reason="No channel could send it -- " + "; ".join(reasons) + ".",
            recipient=None,
            fallback=[],
            occurrence=occurrence,
            actor_id=actor_id,
            attach=False,
        )

    def _variables(
        self, document: MessagingDocument, customer: Customer | None, firm_id: UUID
    ) -> dict[str, str]:
        """Return every variable an event may use, by name."""
        firm = FirmMetadataReader(self._session).get(firm_id)
        return {
            "customer_name": (
                ""
                if customer is None
                else (customer.display_name or customer.name or "")
            ),
            "document_number": document.document_number,
            "document_date": day(document.document_date),
            "amount": money(document.amount),
            "amount_due": money(document.amount),
            "due_date": day(document.due_date),
            "firm_name": firm.name or "",
            "days_overdue": "",
        }

    def _stage_row(
        self,
        *,
        firm_id: UUID,
        event_code: str,
        document: MessagingDocument,
        config: MessagingEventConfig,
        values: dict[str, str],
        status: str,
        reason: str | None,
        recipient: str | None,
        fallback: list[str],
        occurrence: str | None,
        actor_id: UUID | None,
        attach: bool,
        is_resend: bool = False,
        previous_message_id: UUID | None = None,
        body_override: str | None = None,
    ) -> MessagingOutbox:
        """Add one outbox row, rendered, to the session."""
        event = (
            EVENTS_BY_CODE.get(event_code) or EVENTS_BY_CODE["SALES_INVOICE_APPROVED"]
        )
        account = channel_configs(self._session, firm_id).get(config.channel)
        row = MessagingOutbox(
            firm_id=firm_id,
            event_code=event_code,
            document_type=document.document_type,
            document_id=document.document_id,
            document_number=document.document_number,
            customer_id=document.customer_id,
            channel=config.channel,
            provider=None if account is None else account.provider,
            recipient=recipient,
            status=status,
            reason=reason,
            subject=render(config.subject or event.default_subject, values)[:300],
            body=body_override or render(config.body or event.default_body, values),
            template_name=config.template_name,
            template_language=config.template_language,
            variables=[values.get(name, "") for name in event.variables],
            attach_pdf=attach and config.channel == "EMAIL",
            fallback_channels=fallback,
            occurrence=occurrence,
            dedupe_key=(
                None
                if is_resend or event_code == MANUAL_SEND
                else dedupe_key(
                    event_code, document.document_id, config.channel, occurrence
                )
            ),
            is_resend=is_resend,
            previous_message_id=previous_message_id,
            requested_by=actor_id,
            # None is "as soon as the worker passes".
            next_attempt_at=None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        if status == SKIPPED:
            record_on_timeline(self._session, row, "MESSAGE_SKIPPED")
        return row

    # -- By hand --------------------------------------------------------------

    def send_document(
        self, data: ManualSendRequest, *, firm_id: UUID, actor_id: UUID
    ) -> MessagingOutbox:
        """Queue one document to go now, on one channel, as a person asked.

        Uses the template the firm named for the document's own event, so a
        WhatsApp or SMS send needs one named there first. Commits.
        """
        settings = self._settings_row(firm_id)
        if settings is None or not settings.is_enabled:
            raise ValidationError(
                "Messaging is off for this firm. Switch it on under Settings > "
                "Messaging first."
            )
        why_not = is_usable(channel_configs(self._session, firm_id).get(data.channel))
        if why_not is not None:
            raise ValidationError(f"{_label(data.channel)} cannot send: {why_not}.")
        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == data.document_id,
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        if invoice.status in {"DRAFT", "CANCELLED"}:
            raise ValidationError("Only an approved invoice can be sent.")
        template = next(
            (
                row
                for row in self._event_rows(firm_id)
                if row.event_code == "SALES_INVOICE_APPROVED"
                and row.channel == data.channel
            ),
            None,
        ) or MessagingEventConfig(
            firm_id=firm_id, event_code="SALES_INVOICE_APPROVED", channel=data.channel
        )
        if data.channel != "EMAIL" and not template.template_name:
            raise ValidationError(
                f"Name the {_label(data.channel)} template for 'Invoice approved' "
                "under Settings > Messaging first; "
                f"{_label(data.channel)} sends only registered templates."
            )
        customer = self._session.get(Customer, invoice.customer_id)
        recipient = (data.recipient or "").strip() or None
        if recipient is None:
            recipient, why_not = recipient_for(self._session, customer, data.channel)
            if recipient is None:
                raise ValidationError(f"Cannot send: {why_not}. Enter an address.")
        document = MessagingDocument(
            document_type="SALES_INVOICE",
            document_id=invoice.id,
            document_number=invoice.invoice_number,
            document_date=invoice.invoice_date,
            customer_id=invoice.customer_id,
            amount=invoice.grand_total,
            due_date=invoice.due_date,
        )
        values = self._variables(document, customer, firm_id)
        row = self._stage_row(
            firm_id=firm_id,
            event_code=MANUAL_SEND,
            document=document,
            config=template,
            values=values,
            status=QUEUED,
            reason=None,
            recipient=recipient,
            fallback=[],
            occurrence=None,
            actor_id=actor_id,
            attach=True,
            body_override=(data.message or "").strip() or None,
        )
        record_audit(
            self._session,
            action="message.requested",
            entity_type="messaging_outbox",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "document_number": invoice.invoice_number,
                "channel": data.channel,
                "recipient": recipient,
            },
        )
        self._session.commit()
        return row

    def resend(
        self, message_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> MessagingOutbox:
        """Queue a message again -- the only way anything is sent twice."""
        original = self._session.scalar(
            select(MessagingOutbox).where(
                MessagingOutbox.id == message_id,
                MessagingOutbox.firm_id == firm_id,
                MessagingOutbox.is_deleted.is_(False),
            )
        )
        if original is None:
            raise ResourceNotFoundError("Message not found.")
        if original.status in {QUEUED, "SENDING"}:
            raise ConflictError("That message has not been sent yet.")
        why_not = is_usable(
            channel_configs(self._session, firm_id).get(original.channel)
        )
        if why_not is not None:
            raise ValidationError(f"{_label(original.channel)} cannot send: {why_not}.")
        recipient = original.recipient
        if not recipient:
            customer = (
                None
                if original.customer_id is None
                else self._session.get(Customer, original.customer_id)
            )
            recipient, reason = recipient_for(self._session, customer, original.channel)
            if recipient is None:
                raise ValidationError(f"Cannot resend: {reason}.")
        row = MessagingOutbox(
            firm_id=firm_id,
            event_code=original.event_code,
            document_type=original.document_type,
            document_id=original.document_id,
            document_number=original.document_number,
            customer_id=original.customer_id,
            channel=original.channel,
            provider=original.provider,
            recipient=recipient,
            status=QUEUED,
            subject=original.subject,
            body=original.body,
            template_name=original.template_name,
            template_language=original.template_language,
            variables=list(original.variables or []),
            attach_pdf=original.attach_pdf,
            fallback_channels=[],
            occurrence=original.occurrence,
            dedupe_key=None,
            is_resend=True,
            previous_message_id=original.id,
            requested_by=actor_id,
            next_attempt_at=None,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="message.resent",
            entity_type="messaging_outbox",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"resends": str(original.id), "channel": row.channel},
        )
        self._session.commit()
        return row


def stage_document_event(
    session: Session,
    event_code: str,
    document: MessagingDocument,
    *,
    firm_id: UUID,
    actor_id: UUID | None,
) -> None:
    """Ask for an event's message from inside a document service."""
    MessagingService(session).stage_event(
        event_code, document, firm_id=firm_id, actor_id=actor_id
    )


def overdue_cycle(due: date, today: date, every_days: int) -> tuple[int, int]:
    """Return ``(days_overdue, cycle)``: the first reminder is the day after due."""
    days_overdue = (today - due).days
    return days_overdue, (days_overdue - 1) // max(every_days, 1)


def _known_channel(channel: str) -> None:
    """Refuse a channel this release does not have."""
    if channel not in CHANNELS:
        raise ResourceNotFoundError(f"There is no channel {channel}.")


def _label(channel: str) -> str:
    """Return how a channel is named to a person."""
    return {"EMAIL": "Email", "WHATSAPP": "WhatsApp", "SMS": "SMS"}.get(
        channel, channel
    )


def _preferred_first(
    chain: list[MessagingEventConfig], customer: Customer | None
) -> list[MessagingEventConfig]:
    """Put the customer's preferred channel first, when the event offers it."""
    preferred = None if customer is None else customer.preferred_channel
    if not preferred:
        return list(chain)
    return sorted(chain, key=lambda row: (row.channel != preferred, row.priority))


def _settings_snapshot(row: MessagingSettings) -> dict[str, object]:
    """Return the audited shape of the settings row."""
    return {
        "is_enabled": row.is_enabled,
        "due_soon_days": row.due_soon_days,
        "overdue_every_days": row.overdue_every_days,
    }


def _event_row_snapshot(row: MessagingEventConfig) -> dict[str, object]:
    """Return the audited shape of one event channel."""
    return {
        "channel": row.channel,
        "is_enabled": row.is_enabled,
        "priority": row.priority,
        "template_name": row.template_name,
        "template_language": row.template_language,
    }


def _event_response(
    code: str, label: str, rows: list[MessagingEventConfig]
) -> EventConfigResponse:
    """Describe one event and its channels, in fallback order."""
    ordered = sorted(rows, key=lambda row: row.priority)
    return EventConfigResponse(
        event_code=code,
        label=label,
        is_enabled=any(row.is_enabled for row in ordered),
        channels=[
            EventChannelResponse(
                channel=row.channel,
                is_enabled=row.is_enabled,
                template_name=row.template_name,
                template_language=row.template_language,
                subject=row.subject,
                body=row.body,
                priority=row.priority,
            )
            for row in ordered
        ],
    )


#: Re-exported for the worker's reminder scan.
__all__ = [
    "MessagingService",
    "dedupe_key",
    "overdue_cycle",
    "stage_document_event",
]
