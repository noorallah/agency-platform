"""Send what the outbox holds, retry what failed, scan for reminders.

One pass over one firm's store is :func:`process_firm`. The server runs it on
a timer in a background thread (:class:`MessagingWorker`); ``agency-server
messaging-run-once`` runs one pass over every firm for tests and operators.

**Once only.** A row is marked SENDING and committed *before* the provider is
called. If the process dies mid-send, the next pass finds it still SENDING and
marks it failed with a note to resend -- never sends it again by itself,
because whether the first attempt reached the customer cannot be known. A
person pressing *Resend* is the only way a message goes twice.

**Failure.** A provider that refuses (bad credentials, an unknown template)
marks the channel *needs attention* at once and the message falls to the next
channel the event names. One that cannot be reached is retried with back-off;
after the last attempt it is treated the same way.

**Held for the IRN.** An email attaching a B2B invoice the firm must
e-invoice waits, still QUEUED and saying why, until the invoice has its IRN
(77 row 6): the PDF without one is not a valid tax invoice. It is looked at
again every :data:`IRN_RECHECK` and goes out on the first pass after the
registration, so approving and registering in either order sends one email.
"""

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security.secret_box import SecretBoxError
from app.core.utils.dates import as_utc, utc_now
from app.customers.models import Customer
from app.messaging.events import EVENTS_BY_CODE
from app.messaging.models import (
    MessagingEventConfig,
    MessagingOutbox,
    MessagingSettings,
)
from app.messaging.providers import Attachment, OutgoingMessage, ProviderError
from app.messaging.services.common import (
    DELIVERED,
    FAILED,
    HEALTH_NEEDS_ATTENTION,
    QUEUED,
    READ,
    SENDING,
    SENT,
    MessagingDocument,
    adapter_for,
    channel_configs,
    is_usable,
    logger,
    money,
    recipient_for,
    record_on_timeline,
)
from app.messaging.services.messaging_service import (
    MessagingService,
    dedupe_key,
    overdue_cycle,
)
from app.sales_invoice.models import SalesInvoice

#: Minutes to wait before each retry of an unreachable provider.
BACKOFF_MINUTES = (1, 5, 15, 60)
MAX_ATTEMPTS = len(BACKOFF_MINUTES) + 1
#: Rows sent per firm per pass, so one busy firm cannot starve the rest.
BATCH = 50
#: A row SENDING for longer than this was interrupted.
STALE_SENDING = timedelta(minutes=15)
#: How often, and for how long after sending, a status is asked for.
STATUS_EVERY = timedelta(minutes=15)
STATUS_FOR = timedelta(days=3)
#: How long an email held for its invoice's IRN waits before it is looked at
#: again.
IRN_RECHECK = timedelta(minutes=5)


@dataclass(slots=True)
class PassReport:
    """What one pass did, for the CLI and the log."""

    sent: int = 0
    failed: int = 0
    retried: int = 0
    held: int = 0
    skipped: int = 0
    reminders: int = 0
    statuses: int = 0
    errors: list[str] = field(default_factory=list)

    def add(self, other: "PassReport") -> None:
        """Fold another firm's pass into this one."""
        self.sent += other.sent
        self.failed += other.failed
        self.retried += other.retried
        self.held += other.held
        self.skipped += other.skipped
        self.reminders += other.reminders
        self.statuses += other.statuses
        self.errors.extend(other.errors)


def process_firm(
    session: Session, firm_id: UUID, *, now: datetime | None = None
) -> PassReport:
    """Run one pass over one firm: reminders, sends, then statuses."""
    now = now or utc_now()
    report = PassReport()
    settings = session.scalar(
        select(MessagingSettings).where(
            MessagingSettings.firm_id == firm_id,
            MessagingSettings.is_deleted.is_(False),
        )
    )
    if settings is None or not settings.is_enabled:
        # Off means off: what was queued waits until the firm switches it back
        # on, and a firm that never did costs this one query a pass.
        return report
    _scan_reminders(session, settings, now.date(), report)
    _recover_interrupted(session, firm_id, now)
    # Rows waiting -- a retry backing off, an email held for its IRN -- are
    # left out in the query, not after it: a firm with more of them than a
    # page would otherwise never reach the rows behind them.
    due = session.scalars(
        select(MessagingOutbox)
        .where(
            MessagingOutbox.firm_id == firm_id,
            MessagingOutbox.status == QUEUED,
            MessagingOutbox.is_deleted.is_(False),
            or_(
                MessagingOutbox.next_attempt_at.is_(None),
                MessagingOutbox.next_attempt_at <= now,
            ),
        )
        .order_by(MessagingOutbox.created_at, MessagingOutbox.id.asc())
        .limit(BATCH * 4)
    ).all()
    # Checked again here as well: SQLite compares the stored naive value as
    # text, so the query alone is not trusted to have judged the time.
    sendable = [
        row
        for row in due
        if row.next_attempt_at is None or as_utc(row.next_attempt_at) <= now
    ][:BATCH]
    for row in sendable:
        _send_one(session, row, now, report)
    _fetch_statuses(session, firm_id, now, report)
    return report


def _send_one(
    session: Session, row: MessagingOutbox, now: datetime, report: PassReport
) -> None:
    """Send one row, and settle what happened to it."""
    account = channel_configs(session, row.firm_id).get(row.channel)
    why_not = is_usable(account)
    if why_not is not None or account is None:
        _fail(session, row, f"The channel cannot send: {why_not}.", report)
        return
    try:
        adapter = adapter_for(account)
    except (SecretBoxError, KeyError, ValueError) as error:
        account.health = HEALTH_NEEDS_ATTENTION
        account.last_error = str(error)
        _fail(session, row, str(error), report)
        return
    waiting = _waiting_for_irn(session, row)
    if waiting is not None:
        row.reason = waiting
        row.next_attempt_at = now + IRN_RECHECK
        session.commit()
        report.held += 1
        return
    try:
        attachments = _attachments(session, row)
    except Exception as error:  # noqa: BLE001 - recorded on the row
        _fail(session, row, f"The document could not be printed: {error}", report)
        return
    # Claimed and committed before the provider is called: a crash after this
    # point leaves a SENDING row, which is never sent again without a person.
    row.status = SENDING
    row.attempts += 1
    session.commit()
    try:
        result = adapter.send(
            OutgoingMessage(
                to=row.recipient or "",
                subject=row.subject,
                body=row.body,
                template_name=row.template_name,
                template_language=row.template_language,
                variables=tuple(row.variables or ()),
                attachments=attachments,
            )
        )
    except ProviderError as error:
        if not error.permanent and row.attempts < MAX_ATTEMPTS:
            row.status = QUEUED
            row.reason = error.message
            row.next_attempt_at = now + timedelta(
                minutes=BACKOFF_MINUTES[row.attempts - 1]
            )
            session.commit()
            report.retried += 1
            return
        account.health = HEALTH_NEEDS_ATTENTION
        account.last_error = error.message
        _fail(session, row, error.message, report)
        return
    row.status = SENT
    row.reason = None
    row.sent_at = utc_now()
    row.provider_message_id = result.provider_message_id
    record_on_timeline(session, row, "MESSAGE_SENT")
    session.commit()
    report.sent += 1


def _fail(
    session: Session, row: MessagingOutbox, reason: str, report: PassReport
) -> None:
    """Mark a row failed, put it on the timeline, and fall to the next channel."""
    row.status = FAILED
    row.reason = reason[:1000]
    row.next_attempt_at = None
    report.failed += 1
    fallback = _fallback(session, row)
    if fallback is None and row.fallback_channels:
        row.reason = f"{row.reason} No other channel could take it."
    elif fallback is not None:
        row.reason = f"{row.reason} Sent on to {fallback.channel.title()}."
    record_on_timeline(session, row, "MESSAGE_FAILED")
    session.commit()


def _fallback(session: Session, failed: MessagingOutbox) -> MessagingOutbox | None:
    """Queue the message on the next usable channel the event names."""
    remaining = list(failed.fallback_channels or [])
    if not remaining:
        return None
    accounts = channel_configs(session, failed.firm_id)
    templates = {
        row.channel: row
        for row in session.scalars(
            select(MessagingEventConfig).where(
                MessagingEventConfig.firm_id == failed.firm_id,
                MessagingEventConfig.event_code == failed.event_code,
                MessagingEventConfig.is_deleted.is_(False),
            )
        ).all()
    }
    customer = (
        None
        if failed.customer_id is None
        else session.get(Customer, failed.customer_id)
    )
    for index, channel in enumerate(remaining):
        config = templates.get(channel)
        if config is None or not config.is_enabled:
            continue
        if is_usable(accounts.get(channel)) is not None:
            continue
        recipient, why_not = recipient_for(session, customer, channel)
        if recipient is None or why_not is not None:
            continue
        key = (
            None
            if failed.dedupe_key is None
            else dedupe_key(
                failed.event_code, failed.document_id, channel, failed.occurrence
            )
        )
        if key is not None and session.scalar(
            select(MessagingOutbox.id).where(
                MessagingOutbox.firm_id == failed.firm_id,
                MessagingOutbox.dedupe_key == key,
                MessagingOutbox.is_deleted.is_(False),
            )
        ):
            continue
        event = EVENTS_BY_CODE.get(failed.event_code)
        row = MessagingOutbox(
            firm_id=failed.firm_id,
            event_code=failed.event_code,
            document_type=failed.document_type,
            document_id=failed.document_id,
            document_number=failed.document_number,
            customer_id=failed.customer_id,
            channel=channel,
            provider=accounts[channel].provider,
            recipient=recipient,
            status=QUEUED,
            subject=failed.subject,
            body=failed.body,
            template_name=config.template_name,
            template_language=config.template_language,
            variables=list(failed.variables or []),
            attach_pdf=bool(event and event.attaches_pdf and channel == "EMAIL"),
            fallback_channels=remaining[index + 1 :],
            occurrence=failed.occurrence,
            dedupe_key=key,
            is_resend=failed.is_resend,
            previous_message_id=failed.id,
            requested_by=failed.requested_by,
            next_attempt_at=None,
            created_by=failed.requested_by,
            updated_by=failed.requested_by,
        )
        session.add(row)
        session.flush()
        return row
    return None


def _waiting_for_irn(session: Session, row: MessagingOutbox) -> str | None:
    """Say why an email attaching an invoice must wait for its IRN, if it must."""
    if not row.attach_pdf or row.channel != "EMAIL" or row.document_id is None:
        return None
    if row.document_type != "SALES_INVOICE":
        return None
    invoice = session.get(SalesInvoice, row.document_id)
    if invoice is None or invoice.firm_id != row.firm_id:
        return None
    from app.einvoice.services.issue_gate import missing_irn

    reason = missing_irn(
        session,
        firm_scope=row.firm_id,
        number=invoice.invoice_number,
        on=invoice.invoice_date,
        customer_id=invoice.customer_id,
        status=invoice.status,
        sales_invoice_id=invoice.id,
    )
    if reason is None:
        return None
    return (
        f"Waiting for {invoice.invoice_number}'s IRN: it goes out on the first "
        "pass after the invoice is registered on the portal."
    )


def _attachments(session: Session, row: MessagingOutbox) -> tuple[Attachment, ...]:
    """Render the document's PDF for an email that attaches it."""
    if not row.attach_pdf or row.channel != "EMAIL" or row.document_id is None:
        return ()
    if row.document_type == "CUSTOMER_STATEMENT":
        # A payment reminder (MSG-3): the statement as it stood the day it was
        # asked for, which a pass later the same day reproduces exactly.
        from app.customers.services.statement_pdf import CustomerStatementPdfService

        pdf, filename = CustomerStatementPdfService(session).render(
            row.document_id,
            firm_id=row.firm_id,
            to_date=as_utc(row.created_at).date(),
        )
        return (Attachment(filename=filename, content=pdf),)
    if row.document_type != "SALES_INVOICE":
        # A document sent by hand (MSG-4): its own PDF, rendered now.
        from app.messaging.services.hand_documents import render_attachment

        rendered = render_attachment(
            session,
            firm_id=row.firm_id,
            document_type=row.document_type or "",
            document_id=row.document_id,
            on=as_utc(row.created_at).date(),
        )
        if rendered is None:
            return ()
        pdf, filename = rendered
        return (Attachment(filename=filename, content=pdf),)
    # Imported here: the print service pulls in reportlab, which a pass with
    # nothing to attach should not pay for.
    from app.sales_invoice.services.invoice_print_service import (
        SalesInvoicePrintService,
    )

    pdf, filename = SalesInvoicePrintService(session).render(
        row.document_id, firm_scope=row.firm_id
    )
    return (Attachment(filename=filename, content=pdf),)


def _recover_interrupted(session: Session, firm_id: UUID, now: datetime) -> None:
    """Fail a row left SENDING by a process that died mid-send."""
    stale = session.scalars(
        select(MessagingOutbox).where(
            MessagingOutbox.firm_id == firm_id,
            MessagingOutbox.status == SENDING,
            MessagingOutbox.is_deleted.is_(False),
        )
    ).all()
    for row in stale:
        if now - as_utc(row.updated_at) < STALE_SENDING:
            continue
        row.status = FAILED
        row.reason = (
            "Interrupted while sending: it may or may not have reached the "
            "customer, so it is not sent again by itself. Use Resend if it "
            "did not arrive."
        )
        record_on_timeline(session, row, "MESSAGE_FAILED")
    session.commit()


def _fetch_statuses(
    session: Session, firm_id: UUID, now: datetime, report: PassReport
) -> None:
    """Ask the provider what became of recently sent messages, where it can say."""
    rows = session.scalars(
        select(MessagingOutbox).where(
            MessagingOutbox.firm_id == firm_id,
            MessagingOutbox.status.in_((SENT, DELIVERED)),
            MessagingOutbox.provider_message_id.is_not(None),
            MessagingOutbox.is_deleted.is_(False),
        )
    ).all()
    accounts = channel_configs(session, firm_id)
    for row in rows:
        if row.sent_at is None or now - as_utc(row.sent_at) > STATUS_FOR:
            continue
        if row.status_checked_at is not None and (
            now - as_utc(row.status_checked_at) < STATUS_EVERY
        ):
            continue
        account = accounts.get(row.channel)
        if account is None or account.provider != row.provider:
            continue
        try:
            adapter = adapter_for(account)
        except (SecretBoxError, KeyError, ValueError):
            continue
        if not adapter.supports_status:
            continue
        try:
            status = adapter.fetch_status(row.provider_message_id or "")
        except ProviderError:
            status = None
        row.status_checked_at = now
        if status in {DELIVERED, READ} and status != row.status:
            row.status = status
            row.delivered_at = row.delivered_at or now
            report.statuses += 1
        elif status == FAILED:
            row.status = FAILED
            row.reason = "The provider reports it was not delivered."
            record_on_timeline(session, row, "MESSAGE_FAILED")
            report.statuses += 1
    session.commit()


def _scan_reminders(
    session: Session, settings: MessagingSettings, today: date, report: PassReport
) -> None:
    """Once a UTC day: stage due-soon and overdue reminders for unpaid bills."""
    if settings.last_reminder_scan_on == today:
        return
    firm_id = settings.firm_id
    wanted = {
        code
        for (code,) in session.execute(
            select(MessagingEventConfig.event_code).where(
                MessagingEventConfig.firm_id == firm_id,
                MessagingEventConfig.event_code.in_(
                    ("PAYMENT_DUE_SOON", "PAYMENT_OVERDUE")
                ),
                MessagingEventConfig.is_enabled.is_(True),
                MessagingEventConfig.is_deleted.is_(False),
            )
        ).all()
    }
    if wanted:
        # Imported here: settlements imports half the application, and a firm
        # that sends no reminders should not pay for it every pass.
        from app.settlements.services.settlement_service import ReceiptService

        owed = [
            record
            for record in ReceiptService(session).outstanding_invoices(
                firm_id=firm_id, party_id=None
            )
            if record.due_date is not None and record.outstanding_amount > 0
        ]
        invoices = (
            {
                row.id: row
                for row in session.scalars(
                    select(SalesInvoice).where(
                        SalesInvoice.firm_id == firm_id,
                        SalesInvoice.id.in_([record.invoice_id for record in owed]),
                    )
                ).all()
            }
            if owed
            else {}
        )
        service = MessagingService(session)
        for record in owed:
            invoice = invoices.get(record.invoice_id)
            due = record.due_date
            if invoice is None or due is None:
                continue
            document = MessagingDocument(
                document_type="SALES_INVOICE",
                document_id=invoice.id,
                document_number=invoice.invoice_number,
                document_date=invoice.invoice_date,
                customer_id=invoice.customer_id,
                amount=record.outstanding_amount,
                due_date=due,
            )
            if "PAYMENT_DUE_SOON" in wanted and 0 <= (due - today).days <= (
                settings.due_soon_days
            ):
                staged = service.stage_event(
                    "PAYMENT_DUE_SOON",
                    document,
                    firm_id=firm_id,
                    actor_id=None,
                    occurrence=f"DUE-{due.isoformat()}",
                )
                _count(staged, report)
            # A bill long past due is the firm's to chase by hand, not a
            # message the day reminders are switched on (decision A12).
            if (
                "PAYMENT_OVERDUE" in wanted
                and due < today
                and (today - due).days <= settings.overdue_stop_after_days
            ):
                days_overdue, cycle = overdue_cycle(
                    due, today, settings.overdue_every_days
                )
                staged = service.stage_event(
                    "PAYMENT_OVERDUE",
                    document,
                    firm_id=firm_id,
                    actor_id=None,
                    occurrence=f"OVERDUE-{cycle}",
                    variables={
                        "days_overdue": str(days_overdue),
                        "amount_due": money(record.outstanding_amount),
                    },
                )
                _count(staged, report)
    settings.last_reminder_scan_on = today
    session.commit()


def _count(staged: MessagingOutbox | None, report: PassReport) -> None:
    """Tally a staged reminder."""
    if staged is None:
        return
    if staged.status == QUEUED:
        report.reminders += 1
    else:
        report.skipped += 1


#: Opens one firm's store as a session; raises for one it cannot reach.
StoreOpener = Callable[[UUID], AbstractContextManager[Session]]


def process_every_firm(
    firm_ids: Callable[[], list[UUID]], open_store: StoreOpener
) -> PassReport:
    """Run one pass over every firm, reporting a store it could not read."""
    total = PassReport()
    for firm_id in firm_ids():
        try:
            with open_store(firm_id) as session:
                total.add(process_firm(session, firm_id))
        except Exception as error:  # noqa: BLE001 - one firm never stops the rest
            logger.warning("messaging pass failed for firm %s: %s", firm_id, error)
            total.errors.append(f"{firm_id}: {type(error).__name__}: {error}")
    return total


class MessagingWorker:
    """Run :func:`process_every_firm` on a timer in a daemon thread."""

    def __init__(
        self,
        firm_ids: Callable[[], list[UUID]],
        open_store: StoreOpener,
        *,
        interval_seconds: int,
    ) -> None:
        """Hold what a pass needs; start nothing yet."""
        self._firm_ids = firm_ids
        self._open_store = open_store
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread; the first pass waits one interval."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="messaging-outbox", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Ask the thread to stop and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Pass, sleep, repeat -- never let one failure end the loop."""
        while not self._stop.wait(self._interval):
            try:
                report = process_every_firm(self._firm_ids, self._open_store)
                if report.sent or report.failed or report.errors:
                    logger.info(
                        "messaging pass: sent=%s failed=%s retried=%s "
                        "reminders=%s errors=%s",
                        report.sent,
                        report.failed,
                        report.retried,
                        report.reminders,
                        len(report.errors),
                    )
            except Exception:  # noqa: BLE001
                logger.exception("messaging pass failed")
