"""Messaging -- email, WhatsApp and SMS, switched on by each firm (BACKLOG 51).

What the owner decided on 2026-10-01, and what each test pins:

* off by default, and off changes nothing about a document;
* a channel cannot be switched on until its Test has passed, and a provider
  failure marks it *needs attention* and falls to the next channel;
* credentials are sealed at rest and never come back out -- not in a
  response, an audit row or a log line;
* one message per event, document and channel: Resend is the only way to send
  twice, and a document that rolls back leaves no message behind;
* reminders respect the customer's *no reminders*, and only the events the
  firm chose are sent.

No test reaches a network: providers are fakes registered in ``ADAPTERS``,
or the real adapters with their transport replaced.
"""

import json
import logging
import smtplib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ValidationError
from app.core.logging.operations import log_operation
from app.core.security.secret_box import SecretBoxError, open_sealed, seal
from app.customers.models import Customer
from app.document_framework.models import DocumentLifecycleEvent
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES
from app.messaging.api.router import (
    list_messages,
    list_messaging_channels,
    resend_message,
    save_messaging_channel,
    send_document,
)
from app.messaging.api.router import (
    test_messaging_channel as run_channel_test,
)
from app.messaging.models import MessagingChannelConfig, MessagingOutbox
from app.messaging.providers import (
    ADAPTERS,
    MessagingAdapter,
    OutgoingMessage,
    ProviderError,
    ProviderField,
    SendResult,
    http,
    smtp,
)
from app.messaging.schemas import (
    ChannelAccountWrite,
    EventChannelWrite,
    EventConfigWrite,
    ManualSendRequest,
    MessagingSettingsWrite,
)
from app.messaging.services import MessagingService
from app.messaging.services import common as messaging_common
from app.messaging.services.outbox_worker import process_firm
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

SECRET = "S3cret-Value-That-Must-Not-Leak"


@dataclass
class _Provider:
    """What the fakes were asked to do, and how they should behave."""

    sent: list[tuple[str, OutgoingMessage]] = field(default_factory=list)
    #: Per channel: None works, "permanent" refuses, "transient" times out.
    fail: dict[str, str | None] = field(default_factory=dict)
    test_fails: dict[str, bool] = field(default_factory=dict)


_STATE = _Provider()


def _fake(channel_code: str) -> type[MessagingAdapter]:
    """Build a fake provider for one channel."""

    class Fake(MessagingAdapter):
        """A provider that records instead of sending."""

        provider: ClassVar[str] = f"FAKE_{channel_code}"
        channel: ClassVar[str] = channel_code
        label: ClassVar[str] = f"Fake {channel_code}"

        @classmethod
        def required_fields(cls) -> tuple[ProviderField, ...]:
            """Return one public and one secret field."""
            return (
                ProviderField("account", "Account"),
                ProviderField("api_key", "Key", secret=True, kind="password"),
            )

        def test_connection(self) -> None:
            """Pass unless the test asked for a failure."""
            if _STATE.test_fails.get(channel_code):
                raise ProviderError("The provider refused the key.", permanent=True)

        def send(self, message: OutgoingMessage) -> SendResult:
            """Record the message, or fail as asked."""
            mode = _STATE.fail.get(channel_code)
            if mode == "permanent":
                raise ProviderError("Template not approved.", permanent=True)
            if mode == "transient":
                raise ProviderError("Timed out.", permanent=False)
            _STATE.sent.append((channel_code, message))
            return SendResult(provider_message_id=f"id-{len(_STATE.sent)}")

    return Fake


@pytest.fixture(autouse=True)
def _fakes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Register the fakes and start each test with a clean record."""
    global _STATE
    _STATE = _Provider()
    for channel_code in ("EMAIL", "WHATSAPP", "SMS"):
        adapter = _fake(channel_code)
        monkeypatch.setitem(ADAPTERS, adapter.provider, adapter)

    def no_network(*_: object) -> object:
        """Fail loudly if anything reaches for a network."""
        raise AssertionError("a test reached for the network")

    monkeypatch.setattr(http, "transport", no_network)
    monkeypatch.setattr(smtp, "connect", no_network)
    # Printing the invoice is not what these tests are about.
    monkeypatch.setattr(
        "app.messaging.services.outbox_worker._attachments", lambda *_: ()
    )
    yield


class _Shop(_Firm):
    """A firm that sells, with a customer who can be reached every way."""

    def __init__(self) -> None:
        """Build the firm and give the customer an email and a phone."""
        super().__init__(_session_factory()())
        self.actor_id = uuid4()
        self.customer.email = "buyer@example.com"
        self.customer.phone = "+919876543210"
        self.session.commit()
        # A counter firm: a bare bill raises its own order and delivery note.
        self.stages(quotation=False, sales_order=False, delivery_note=False)
        self.messaging = MessagingService(self.session)

    def switch_on(self, *, overdue_every: int = 7, stop_after: int = 90) -> None:
        """Turn messaging on for the firm."""
        self.messaging.update_settings(
            MessagingSettingsWrite(
                is_enabled=True,
                due_soon_days=3,
                overdue_every_days=overdue_every,
                overdue_stop_after_days=stop_after,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def channel(self, channel: str, *, enable: bool = True) -> None:
        """Save a fake account for a channel, test it and switch it on."""
        self.messaging.save_account(
            channel,
            ChannelAccountWrite(
                provider=f"FAKE_{channel}",
                settings={"account": "acct-1", "api_key": SECRET},
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.messaging.test_channel(
            channel, firm_id=self.firm.id, actor_id=self.actor_id
        )
        if enable:
            self.messaging.set_channel_enabled(
                channel, True, firm_id=self.firm.id, actor_id=self.actor_id
            )

    def event(self, code: str, *channels: str, template: str | None = "tpl") -> None:
        """Send an event on these channels, in this order."""
        self.messaging.save_event_config(
            code,
            EventConfigWrite(
                channels=[
                    EventChannelWrite(channel=channel, template_name=template)
                    for channel in channels
                ]
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def approved_bill(self) -> SalesInvoice:
        """Raise and approve a counter bill."""
        bills = SalesInvoiceService(self.session)
        draft = bills.create_invoice(
            self.bare_bill(), firm_id=self.firm.id, actor_id=self.actor_id
        )
        return bills.approve_invoice(
            draft.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )

    def outbox(self) -> list[MessagingOutbox]:
        """Return every message, oldest first."""
        return list(
            self.session.scalars(
                select(MessagingOutbox).order_by(MessagingOutbox.created_at)
            ).all()
        )

    def timeline(self, document_id: UUID) -> list[DocumentLifecycleEvent]:
        """Return the message events on a document's timeline."""
        return [
            row
            for row in self.session.scalars(
                select(DocumentLifecycleEvent).where(
                    DocumentLifecycleEvent.source_document_id == document_id
                )
            ).all()
            if row.action.startswith("MESSAGE_")
        ]

    def run(self, now: datetime | None = None) -> None:
        """Run one worker pass."""
        process_firm(self.session, self.firm.id, now=now)


@pytest.fixture
def shop() -> _Shop:
    """Build the firm."""
    return _Shop()


def _scope(firm_id: UUID, actor_id: UUID) -> ResolvedFirmScope:
    """Return a resolved scope for calling a route function directly."""
    return ResolvedFirmScope(
        principal=cast(Any, SimpleNamespace(subject=actor_id)), firm_id=firm_id
    )


# -- Off changes nothing --------------------------------------------------------


def test_messaging_off_changes_nothing_about_a_document(shop: _Shop) -> None:
    """No settings row: the bill approves exactly as before, and nothing is kept."""
    bill = shop.approved_bill()
    assert bill.status == "APPROVED"
    assert shop.outbox() == []
    assert shop.timeline(bill.id) == []


def test_a_channel_and_an_event_still_send_nothing_while_the_switch_is_off(
    shop: _Shop,
) -> None:
    """The master switch is the firm's, and off means off."""
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    shop.approved_bill()
    assert shop.outbox() == []


def test_only_the_events_the_firm_chose_are_sent(shop: _Shop) -> None:
    """A receipt event chosen does not make an invoice send; a disabled row neither."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("RECEIPT_POSTED", "EMAIL")
    shop.approved_bill()
    assert shop.outbox() == []

    shop.messaging.save_event_config(
        "SALES_INVOICE_APPROVED",
        EventConfigWrite(
            channels=[EventChannelWrite(channel="EMAIL", is_enabled=False)]
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    shop.approved_bill()
    assert shop.outbox() == []

    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    bill = shop.approved_bill()
    rows = shop.outbox()
    assert [(row.event_code, row.status) for row in rows] == [
        ("SALES_INVOICE_APPROVED", "QUEUED")
    ]
    assert rows[0].document_id == bill.id
    assert rows[0].recipient == "buyer@example.com"
    assert bill.invoice_number in (rows[0].subject or "")


# -- Channels --------------------------------------------------------------------


def test_a_channel_cannot_be_switched_on_until_its_test_has_passed(
    shop: _Shop,
) -> None:
    """Saved is not tested; failed is not tested; only a pass lets it on."""
    shop.channel("EMAIL", enable=False)
    shop.messaging.save_account(
        "EMAIL",
        ChannelAccountWrite(provider="FAKE_EMAIL", settings={"account": "acct-2"}),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    with pytest.raises(ValidationError, match="Test the account first"):
        shop.messaging.set_channel_enabled(
            "EMAIL", True, firm_id=shop.firm.id, actor_id=shop.actor_id
        )

    _STATE.test_fails["EMAIL"] = True
    failed = shop.messaging.test_channel(
        "EMAIL", firm_id=shop.firm.id, actor_id=shop.actor_id
    )
    assert failed.health == "NEEDS_ATTENTION"
    assert failed.last_error == "The provider refused the key."
    with pytest.raises(ValidationError):
        shop.messaging.set_channel_enabled(
            "EMAIL", True, firm_id=shop.firm.id, actor_id=shop.actor_id
        )

    _STATE.test_fails["EMAIL"] = False
    shop.messaging.test_channel("EMAIL", firm_id=shop.firm.id, actor_id=shop.actor_id)
    on = shop.messaging.set_channel_enabled(
        "EMAIL", True, firm_id=shop.firm.id, actor_id=shop.actor_id
    )
    assert on.is_enabled and on.health == "OK"

    # Replacing the account switches it off and asks for a Test again.
    replaced = shop.messaging.save_account(
        "EMAIL",
        ChannelAccountWrite(provider="FAKE_EMAIL", settings={"account": "acct-3"}),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert (replaced.is_enabled, replaced.health) == (False, "UNTESTED")


def test_a_secret_left_blank_keeps_the_one_saved(shop: _Shop) -> None:
    """Changing a public field does not mean retyping the key."""
    shop.channel("EMAIL", enable=False)
    shop.messaging.save_account(
        "EMAIL",
        ChannelAccountWrite(provider="FAKE_EMAIL", settings={"account": "acct-9"}),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    row = shop.session.scalar(select(MessagingChannelConfig))
    assert row is not None and row.credentials_encrypted is not None
    key = messaging_common.credential_key()
    assert key is not None
    assert json.loads(open_sealed(row.credentials_encrypted, secret=key)) == {
        "api_key": SECRET
    }
    assert row.public_settings == {"account": "acct-9"}


def test_a_required_field_must_be_given(shop: _Shop) -> None:
    """A first save without the secret is refused by name."""
    with pytest.raises(ValidationError, match="Key"):
        shop.messaging.save_account(
            "EMAIL",
            ChannelAccountWrite(provider="FAKE_EMAIL", settings={"account": "a"}),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_a_provider_cannot_serve_another_channel(shop: _Shop) -> None:
    """An SMS provider is not an email account."""
    with pytest.raises(ValidationError, match="cannot send email"):
        shop.messaging.save_account(
            "EMAIL",
            ChannelAccountWrite(provider="MSG91", settings={}),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_without_a_key_no_credential_can_be_stored(
    shop: _Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production with no AGENCY_MESSAGING_KEY refuses, and says what to do."""
    monkeypatch.setattr(messaging_common, "credential_key", lambda: None)
    monkeypatch.setattr(
        "app.messaging.services.messaging_service.credential_key", lambda: None
    )
    with pytest.raises(ValidationError, match="AGENCY_MESSAGING_KEY"):
        shop.channel("EMAIL")
    assert shop.messaging.settings_response(shop.firm.id).can_store_credentials is False


def test_production_without_a_key_has_none_and_development_has_one() -> None:
    """The JWT key's shape: development falls back, production does not."""
    from app.core.config.settings import (
        DEVELOPMENT_MESSAGING_KEY,
        Environment,
        Settings,
    )

    development = Settings(environment=Environment.DEVELOPMENT, messaging_key=None)
    assert development.messaging_secret() == DEVELOPMENT_MESSAGING_KEY
    production = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret_key="a-real-production-signing-key-of-some-length",
        database_password="a-real-password",
        bootstrap_admin_password="An-Admin-Password-1!",
        messaging_key=None,
    )
    assert production.messaging_secret() is None
    production_dev_key = production.model_copy(
        update={"messaging_key": SecretStr(DEVELOPMENT_MESSAGING_KEY)}
    )
    assert production_dev_key.messaging_secret() is None


# -- Secrets ----------------------------------------------------------------------


def test_encryption_round_trips_and_refuses_a_wrong_key_or_a_change() -> None:
    """Sealed under one key, opened under it, refused under any other."""
    stored = seal("token-123", secret="key-one")
    assert stored.startswith("v1.")
    assert "token-123" not in stored
    assert open_sealed(stored, secret="key-one") == "token-123"
    assert seal("token-123", secret="key-one") != stored  # a fresh nonce each time
    with pytest.raises(SecretBoxError):
        open_sealed(stored, secret="key-two")
    tampered = stored[:-4] + ("AAAA" if not stored.endswith("AAAA") else "BBBB")
    with pytest.raises(SecretBoxError):
        open_sealed(tampered, secret="key-one")
    long = "x" * 1000
    assert open_sealed(seal(long, secret="k"), secret="k") == long


def test_credentials_never_appear_in_a_response_an_audit_row_or_a_log(
    shop: _Shop, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real SMTP account, a failing Test, and nothing anywhere holds the password."""

    class Refusing:
        """A mail server that refuses the password, echoing it back."""

        def __init__(self, *_: object) -> None:
            """Accept the connection."""

        def starttls(self, **_: object) -> None:
            """Accept STARTTLS."""

        def login(self, user: str, password: str) -> None:
            """Refuse, quoting the password like a careless server might."""
            raise smtplib.SMTPAuthenticationError(535, f"bad {password}".encode())

        def close(self) -> None:
            """Close."""

    monkeypatch.setattr(smtp, "connect", lambda *args: Refusing())
    caplog.set_level(logging.DEBUG)
    scope = _scope(shop.firm.id, shop.actor_id)
    saved = save_messaging_channel(
        "EMAIL",
        ChannelAccountWrite(
            provider="SMTP",
            settings={
                "host": "smtp.example.com",
                "port": "587",
                "username": "billing@example.com",
                "password": SECRET,
                "from_email": "billing@example.com",
            },
        ),
        scope,
        shop.session,
    )
    tested = run_channel_test("EMAIL", scope, shop.session)
    listed = list_messaging_channels(scope, shop.session)
    assert tested.data is not None and tested.data.health == "NEEDS_ATTENTION"
    for response in (saved, tested, listed):
        assert SECRET not in response.model_dump_json()
    assert saved.data is not None and saved.data.secrets_set == ["password"]
    stored = shop.session.scalar(select(MessagingChannelConfig))
    assert stored is not None
    assert SECRET not in json.dumps(stored.public_settings)
    assert SECRET not in (stored.credentials_encrypted or "")
    assert SECRET not in (stored.last_error or "")
    for audit in shop.session.scalars(select(AuditLog)).all():
        assert SECRET not in json.dumps(audit.after_data, default=str)
        assert SECRET not in json.dumps(audit.before_data, default=str)
    assert SECRET not in caplog.text


def test_the_log_redacts_every_provider_key_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """MSG91's authkey and Meta's access_token are on the redaction list."""
    caplog.set_level(logging.INFO, logger="app.operations")
    log_operation(
        "messaging.test",
        authkey=SECRET,
        access_token=SECRET,
        password=SECRET,
        credentials=SECRET,
    )
    assert SECRET not in caplog.text


# -- Sending, failure and fallback -------------------------------------------------


def test_a_queued_message_is_sent_and_put_on_the_timeline(shop: _Shop) -> None:
    """The worker sends it once and the bill's history says so."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    bill = shop.approved_bill()
    shop.run()
    shop.run()
    assert [channel for channel, _ in _STATE.sent] == ["EMAIL"]
    (row,) = shop.outbox()
    assert row.status == "SENT" and row.provider_message_id == "id-1"
    (event,) = shop.timeline(bill.id)
    assert event.action == "MESSAGE_SENT"
    assert event.email_recipient == "buyer@example.com"


def test_a_failing_provider_needs_attention_and_falls_to_the_next_channel(
    shop: _Shop,
) -> None:
    """Email refuses; the channel is flagged; WhatsApp takes the message."""
    shop.customer.whatsapp_opt_in = True
    shop.session.commit()
    shop.switch_on()
    shop.channel("EMAIL")
    shop.channel("WHATSAPP")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL", "WHATSAPP")
    _STATE.fail["EMAIL"] = "permanent"
    bill = shop.approved_bill()
    shop.run()
    shop.run()

    email, whatsapp = shop.outbox()
    assert (email.channel, email.status) == ("EMAIL", "FAILED")
    assert "Template not approved." in (email.reason or "")
    assert (whatsapp.channel, whatsapp.status) == ("WHATSAPP", "SENT")
    assert whatsapp.previous_message_id == email.id
    assert whatsapp.recipient == "+919876543210"
    account = shop.messaging.channel("EMAIL", shop.firm.id)
    assert account.health == "NEEDS_ATTENTION"
    assert [event.action for event in shop.timeline(bill.id)] == [
        "MESSAGE_FAILED",
        "MESSAGE_SENT",
    ]
    # A channel needing attention is passed over at the next request.
    shop.approved_bill()
    assert shop.outbox()[-1].channel == "WHATSAPP"


def test_whatsapp_needs_the_customers_opt_in(shop: _Shop) -> None:
    """Without it the message is skipped with the reason, on the timeline."""
    shop.switch_on()
    shop.channel("WHATSAPP")
    shop.event("SALES_INVOICE_APPROVED", "WHATSAPP")
    bill = shop.approved_bill()
    (row,) = shop.outbox()
    assert row.status == "SKIPPED"
    assert "opted in" in (row.reason or "")
    (event,) = shop.timeline(bill.id)
    assert event.action == "MESSAGE_SKIPPED"


def test_an_unreachable_provider_is_retried_with_back_off(shop: _Shop) -> None:
    """A timeout waits and tries again; it is not a failure yet."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    shop.approved_bill()
    _STATE.fail["EMAIL"] = "transient"
    now = datetime.now(UTC)
    shop.run(now)
    (row,) = shop.outbox()
    assert (row.status, row.attempts) == ("QUEUED", 1)
    assert row.next_attempt_at is not None
    shop.run(now)  # too soon: not tried again
    assert row.attempts == 1
    _STATE.fail["EMAIL"] = None
    shop.run(now + timedelta(minutes=2))
    assert (row.status, row.attempts) == ("SENT", 2)


def test_an_interrupted_send_is_never_sent_again_by_itself(shop: _Shop) -> None:
    """A row left SENDING is failed with a note to resend, not retried."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    shop.approved_bill()
    (row,) = shop.outbox()
    row.status = "SENDING"
    shop.session.commit()
    shop.run(datetime.now(UTC) + timedelta(hours=1))
    assert row.status == "FAILED"
    assert "Resend" in (row.reason or "")
    assert _STATE.sent == []


# -- Once only -------------------------------------------------------------------


def test_a_resend_is_the_only_way_to_send_twice(shop: _Shop) -> None:
    """Asking again for the same event changes nothing; Resend does."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    bill = shop.approved_bill()
    shop.run()
    (first,) = shop.outbox()
    again = shop.messaging.stage_event(
        "SALES_INVOICE_APPROVED",
        messaging_common.MessagingDocument(
            document_type="SALES_INVOICE",
            document_id=bill.id,
            document_number=bill.invoice_number,
            document_date=bill.invoice_date,
            customer_id=bill.customer_id,
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert again is None
    shop.run()
    assert len(_STATE.sent) == 1

    resent = resend_message(first.id, _scope(shop.firm.id, shop.actor_id), shop.session)
    assert resent.data is not None and resent.data.is_resend
    shop.run()
    assert len(_STATE.sent) == 2


def test_a_rolled_back_document_leaves_no_message(shop: _Shop) -> None:
    """The message is staged in the document's own transaction."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    bills = SalesInvoiceService(shop.session)
    draft = bills.create_invoice(
        shop.bare_bill(), firm_id=shop.firm.id, actor_id=shop.actor_id
    )
    bills.stage_approval(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor_id)
    shop.session.flush()
    assert len(shop.outbox()) == 1
    shop.session.rollback()
    assert shop.outbox() == []


def test_a_failure_inside_messaging_never_fails_the_document(
    shop: _Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bug here is logged and swallowed; the bill still approves."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")

    def broken(*_: object, **__: object) -> None:
        """Fail the way an unmigrated store would."""
        raise RuntimeError("no such table: messaging_outbox")

    monkeypatch.setattr(MessagingService, "_stage_event", broken)
    bill = shop.approved_bill()
    assert bill.status == "APPROVED"
    assert shop.outbox() == []


# -- Reminders -------------------------------------------------------------------


def _overdue(shop: _Shop, days: int) -> SalesInvoice:
    """Approve a bill that fell due ``days`` ago."""
    bill = shop.approved_bill()
    bill.due_date = date(2026, 9, 1)
    shop.session.commit()
    return bill


def test_a_customer_who_asked_for_no_reminders_gets_none(shop: _Shop) -> None:
    """The overdue reminder is skipped with the reason; nothing is sent."""
    shop.customer.no_reminders = True
    shop.session.commit()
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("PAYMENT_OVERDUE", "EMAIL")
    bill = _overdue(shop, 10)
    shop.run(datetime(2026, 9, 11, 9, tzinfo=UTC))
    (row,) = shop.outbox()
    assert row.status == "SKIPPED"
    assert row.reason == "The customer asked for no reminders."
    assert [event.action for event in shop.timeline(bill.id)] == ["MESSAGE_SKIPPED"]
    assert _STATE.sent == []


def test_an_overdue_reminder_goes_once_per_cycle(shop: _Shop) -> None:
    """Every n days while owed: a second scan the same cycle sends nothing."""
    shop.switch_on(overdue_every=7)
    shop.channel("EMAIL")
    shop.event("PAYMENT_OVERDUE", "EMAIL")
    _overdue(shop, 0)
    shop.run(datetime(2026, 9, 2, 9, tzinfo=UTC))  # one day overdue
    shop.run(datetime(2026, 9, 5, 9, tzinfo=UTC))  # same cycle
    assert [row.occurrence for row in shop.outbox()] == ["OVERDUE-0"]
    shop.run(datetime(2026, 9, 9, 9, tzinfo=UTC))  # eight days: next cycle
    assert [row.occurrence for row in shop.outbox()] == ["OVERDUE-0", "OVERDUE-1"]
    assert all(row.status == "SENT" for row in shop.outbox())
    assert (
        "8" in shop.outbox()[1].variables
    )  # days overdue, in order  # type: ignore[operator]


def test_a_bill_overdue_longer_than_the_window_is_not_reminded(shop: _Shop) -> None:
    """Decision A12: switching reminders on does not chase every old bill.

    Due 1 September, a 30-day window: reminded on the 30th day overdue, not on
    the 31st -- and not on switching on in December either.
    """
    shop.switch_on(overdue_every=1, stop_after=30)
    shop.channel("EMAIL")
    shop.event("PAYMENT_OVERDUE", "EMAIL")
    _overdue(shop, 0)
    shop.run(datetime(2026, 10, 1, 9, tzinfo=UTC))  # 30 days overdue
    assert len(shop.outbox()) == 1
    shop.run(datetime(2026, 10, 2, 9, tzinfo=UTC))  # 31: past the window
    shop.run(datetime(2026, 12, 1, 9, tzinfo=UTC))
    assert len(shop.outbox()) == 1


def test_the_window_defaults_to_ninety_days(shop: _Shop) -> None:
    """A firm that never chose stops at 90."""
    assert shop.messaging.settings_response(shop.firm.id).overdue_stop_after_days == 90


def test_a_due_soon_reminder_goes_once_before_the_due_date(shop: _Shop) -> None:
    """Within n days of the due date, once."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("PAYMENT_DUE_SOON", "EMAIL")
    bill = shop.approved_bill()
    bill.due_date = date(2026, 9, 10)
    shop.session.commit()
    shop.run(datetime(2026, 9, 5, 9, tzinfo=UTC))  # five days out: not yet
    assert shop.outbox() == []
    shop.run(datetime(2026, 9, 7, 9, tzinfo=UTC))
    shop.run(datetime(2026, 9, 8, 9, tzinfo=UTC))
    assert [row.event_code for row in shop.outbox()] == ["PAYMENT_DUE_SOON"]


# -- By hand ---------------------------------------------------------------------


def test_a_bill_can_be_sent_by_hand(shop: _Shop) -> None:
    """Send queues the bill on the chosen channel, without an event chosen."""
    shop.switch_on()
    shop.channel("EMAIL")
    bill = shop.approved_bill()
    queued = send_document(
        ManualSendRequest(document_id=bill.id, channel="EMAIL"),
        _scope(shop.firm.id, shop.actor_id),
        shop.session,
    )
    assert queued.data is not None and queued.data.status == "QUEUED"
    shop.run()
    assert len(_STATE.sent) == 1
    # Sending by hand again is a deliberate act and is allowed.
    send_document(
        ManualSendRequest(document_id=bill.id, channel="EMAIL"),
        _scope(shop.firm.id, shop.actor_id),
        shop.session,
    )
    shop.run()
    assert len(_STATE.sent) == 2


def test_sending_by_hand_refuses_while_messaging_is_off(shop: _Shop) -> None:
    """The firm has to have switched it on."""
    bill = shop.approved_bill()
    with pytest.raises(ValidationError, match="Messaging is off"):
        shop.messaging.send_document(
            ManualSendRequest(document_id=bill.id, channel="EMAIL"),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_whatsapp_by_hand_needs_a_named_template(shop: _Shop) -> None:
    """WhatsApp delivers only approved templates, so one must be named first."""
    shop.customer.whatsapp_opt_in = True
    shop.session.commit()
    shop.switch_on()
    shop.channel("WHATSAPP")
    bill = shop.approved_bill()
    with pytest.raises(ValidationError, match="template"):
        shop.messaging.send_document(
            ManualSendRequest(document_id=bill.id, channel="WHATSAPP"),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_the_log_lists_messages_newest_first(shop: _Shop) -> None:
    """The message log is paginated and filterable."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    shop.approved_bill()
    shop.approved_bill()
    page = list_messages(
        _scope(shop.firm.id, shop.actor_id),
        page=1,
        page_size=1,
        search=None,
        status_value="QUEUED",
        channel=None,
        event_code=None,
        document_id=None,
        db=shop.session,
    )
    assert page.pagination.total_records == 2
    assert len(page.data) == 1


# -- Permissions -----------------------------------------------------------------


def test_sending_is_its_own_seeded_permission() -> None:
    """DOCUMENT_SEND is seeded; the firm administrator holds it and the settings."""
    assert "DOCUMENT_SEND" in SYSTEM_PERMISSION_CODES
    assert {
        "DOCUMENT_SEND",
        "SETTINGS_VIEW",
        "SETTINGS_UPDATE",
    } <= ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "DOCUMENT_SEND" in ROLE_PERMISSION_CODES["SALES_MANAGER"]
    assert "SETTINGS_UPDATE" not in ROLE_PERMISSION_CODES["SALES_MANAGER"]


# -- The customer's preferences ----------------------------------------------------


def test_the_whatsapp_opt_in_is_dated_by_the_server(shop: _Shop) -> None:
    """Ticked records when; omitted leaves it; unticked clears it."""
    from app.customers.schemas import CustomerCreate, CustomerUpdate
    from app.customers.services import CustomerService

    service = CustomerService(shop.session)
    base = {
        "code": "MSG-01",
        "customer_type": "INDIVIDUAL",
        "name": "Opted In",
        "currency_code": "INR",
    }
    created = service.create(
        CustomerCreate.model_validate(
            base
            | {
                "whatsapp_opt_in": True,
                "preferred_channel": "WHATSAPP",
                "no_reminders": True,
            }
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert created.whatsapp_opt_in and created.whatsapp_opt_in_at is not None
    assert (created.preferred_channel, created.no_reminders) == ("WHATSAPP", True)
    stamped = created.whatsapp_opt_in_at
    updated = service.update(
        created.id,
        CustomerUpdate.model_validate(base | {"name": "Opted In Ltd"}),
        firm_scope=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert updated.whatsapp_opt_in_at == stamped and updated.no_reminders
    cleared = service.update(
        created.id,
        CustomerUpdate.model_validate(base | {"whatsapp_opt_in": False}),
        firm_scope=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert not cleared.whatsapp_opt_in and cleared.whatsapp_opt_in_at is None
    assert isinstance(shop.session.get(Customer, created.id), Customer)


def test_switching_messaging_off_holds_what_was_queued(shop: _Shop) -> None:
    """Off stops sending at once; switching back on sends what waited."""
    shop.switch_on(overdue_every=9)
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    shop.approved_bill()
    shop.messaging.update_settings(
        MessagingSettingsWrite.model_validate({"is_enabled": False}),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    # Absent fields stay as they were (exclude_unset on update).
    assert shop.messaging.settings_response(shop.firm.id).overdue_every_days == 9
    shop.run()
    assert _STATE.sent == []
    shop.switch_on()
    shop.run()
    assert len(_STATE.sent) == 1


# -- No invoice goes out before its IRN (backlog 77 row 6) ----------------------


def _einvoicing_b2b(shop: _Shop) -> None:
    """Make the firm e-invoice and the customer a registered buyer."""
    from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
    from app.tax.services.gst_compliance import GstComplianceService

    shop.customer.gst_number = "27AAPFU0939F1ZV"
    shop.session.commit()
    GstComplianceService(shop.session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=date(2020, 1, 1),
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )


def _registered(shop: _Shop, bill: SalesInvoice) -> None:
    """Record the bill's IRN as the portal would have issued it."""
    from app.einvoice.models import EInvoiceRegistration

    shop.session.add(
        EInvoiceRegistration(
            firm_id=shop.firm.id,
            sales_invoice_id=bill.id,
            mode="SANDBOX",
            status="REGISTERED",
            irn="a" * 64,
        )
    )
    shop.session.commit()


def test_an_email_waits_for_the_invoices_irn_then_goes_once(shop: _Shop) -> None:
    """Held, saying why, while there is no IRN; sent on the pass after it."""
    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    _einvoicing_b2b(shop)
    bill = shop.approved_bill()
    now = datetime.now(UTC)

    shop.run(now)
    (row,) = shop.outbox()
    assert _STATE.sent == []
    assert row.status == "QUEUED" and row.attempts == 0
    assert row.reason is not None and "IRN" in row.reason

    _registered(shop, bill)
    shop.run(now + timedelta(minutes=1))
    assert _STATE.sent == [], "not looked at again before the recheck"
    shop.run(now + timedelta(minutes=10))
    assert [channel for channel, _ in _STATE.sent] == ["EMAIL"]
    assert shop.outbox()[0].status == "SENT"


def test_a_held_email_does_not_hold_up_the_rest_of_the_queue(shop: _Shop) -> None:
    """Rows waiting are left out of the page, so they cannot crowd it."""
    from app.messaging.services import outbox_worker

    shop.switch_on()
    shop.channel("EMAIL")
    shop.event("SALES_INVOICE_APPROVED", "EMAIL")
    _einvoicing_b2b(shop)
    now = datetime.now(UTC)
    for _ in range(4):
        shop.approved_bill()
    shop.run(now)
    assert len(shop.outbox()) == 4 and _STATE.sent == []

    shop.customer.gst_number = None
    shop.session.commit()
    shop.approved_bill()
    original = outbox_worker.BATCH
    outbox_worker.BATCH = 1
    try:
        # A page is four rows. Four rows wait ahead of the new one, so it is
        # reached only because waiting rows are filtered in the query.
        shop.run(now + timedelta(minutes=1))
    finally:
        outbox_worker.BATCH = original
    assert len(_STATE.sent) == 1


def test_sending_an_unregistered_b2b_bill_by_email_is_refused(shop: _Shop) -> None:
    """By hand, the refusal is immediate and names the way out."""
    from app.core.exceptions import BusinessRuleError

    shop.switch_on()
    shop.channel("EMAIL")
    _einvoicing_b2b(shop)
    bill = shop.approved_bill()
    with pytest.raises(BusinessRuleError, match="has no IRN yet") as refused:
        shop.messaging.send_document(
            ManualSendRequest(document_id=bill.id, channel="EMAIL"),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )
    assert refused.value.details == {"reason": "irn_required"}
    assert shop.outbox() == []

    _registered(shop, bill)
    shop.messaging.send_document(
        ManualSendRequest(document_id=bill.id, channel="EMAIL"),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert len(shop.outbox()) == 1
