"""What is still to be registered, and the 30-day limit (backlog 77 row 7, A44).

GSTN advisory of 5 November 2024: from 1 April 2025 a taxpayer with an
aggregate turnover of 10 crore or more may not report a document to the IRP
more than 30 days after its date -- invoices, credit notes and debit notes
alike. The IRP refuses it and issues no IRN, and a B2B invoice with no IRN is
no invoice (rule 48(5)), so a document that misses the window can only be
replaced: cancelled in the books and raised again under today's date.

The firm says from when the limit binds it (``thirty_day_rule_from`` on its
GST document settings), because only the firm knows its turnover. From that
day, registering -- through the portal or in an offline export -- refuses a
document past its last day, naming the day; and the list of documents still
to be registered shows how many days each has left, flagging those within
:data:`DUE_SOON_DAYS` of it, the way ClearTax and India Compliance (ERPNext)
show a pending e-invoice's remaining days.

The list itself needs no limit: a firm that must e-invoice wants to see every
B2B document that has no IRN, whether or not the 30-day limit applies to it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.common.firm_metadata import firm_today
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.einvoice.models import EInvoiceRegistration
from app.sales_invoice.models import SalesInvoice

#: Days after its date within which the IRP accepts a document.
REPORTING_DAYS = 30
#: Days left at which the list flags a document as due soon.
DUE_SOON_DAYS = 5

OPEN = "OPEN"
DUE_SOON = "DUE_SOON"
LATE = "LATE"


@dataclass(frozen=True, slots=True)
class PendingDocument:
    """One document the firm must register and has not."""

    document_type: str
    document_id: UUID
    number: str
    on: date
    customer_name: str
    amount: object
    registration_status: str | None
    registration_error: str | None
    last_day: date | None
    days_left: int | None
    state: str


def _rule_from(session: Session, firm_scope: UUID) -> date | None:
    """Return the day the 30-day limit binds the firm from, if it does."""
    from app.tax.services.gst_compliance import GstComplianceService

    return (
        GstComplianceService(session).settings_response(firm_scope)
    ).thirty_day_rule_from


def last_day(
    session: Session, *, firm_scope: UUID, on: date, today: date | None = None
) -> date | None:
    """Return the last day a document dated ``on`` may be registered.

    None while the limit does not bind the firm: it never chose a date, or
    the date has not come yet.
    """
    since = _rule_from(session, firm_scope)
    today = today or firm_today(session, firm_scope)
    if since is None or today < since:
        return None
    return on + timedelta(days=REPORTING_DAYS)


def refuse_if_late(
    session: Session,
    *,
    firm_scope: UUID,
    number: str,
    on: date,
    today: date | None = None,
) -> None:
    """Refuse to register a document the IRP would refuse as too old.

    Raises:
        ValidationError: When the firm is bound by the limit and the
            document's last day has passed.

    """
    today = today or firm_today(session, firm_scope)
    deadline = last_day(session, firm_scope=firm_scope, on=on, today=today)
    if deadline is None or today <= deadline:
        return
    raise ValidationError(
        f"{number} is dated {on:%d %b %Y}; the last day to register it was "
        f"{deadline:%d %b %Y}. The IRP refuses a document more than "
        f"{REPORTING_DAYS} days old from a firm with turnover of 10 crore or "
        "more (GSTN advisory, 5 Nov 2024), and without an IRN it is not a "
        "valid invoice. Cancel it and raise it again under today's date."
    )


def _state(days_left: int | None) -> str:
    """Name how close a document is to its last day."""
    if days_left is None:
        return OPEN
    if days_left < 0:
        return LATE
    if days_left <= DUE_SOON_DAYS:
        return DUE_SOON
    return OPEN


def pending(
    session: Session, firm_scope: UUID, *, today: date | None = None
) -> list[PendingDocument]:
    """List every approved B2B document the firm must register and has not.

    From the firm's *e-invoicing applies from* date; oldest first, because the
    oldest is the one about to run out of days. A document with a refused or
    exported-and-waiting registration is listed with that status.
    """
    from app.credit_note.models import CreditNote
    from app.customer_debit_note.models import CustomerDebitNote
    from app.sales_return.billing import returns_crediting_bills
    from app.sales_return.models import SalesReturn
    from app.tax.services.gst_compliance import GstComplianceService

    since = (
        GstComplianceService(session).settings_response(firm_scope)
    ).einvoice_applicable_from
    if since is None:
        return []
    today = today or firm_today(session, firm_scope)
    rule_from = _rule_from(session, firm_scope)
    binds = rule_from is not None and today >= rule_from
    b2b = and_(
        Customer.gst_number.is_not(None),
        func.trim(Customer.gst_number) != "",
    )
    kinds = (
        (
            "SALES_INVOICE",
            SalesInvoice,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            SalesInvoice.grand_total,
            EInvoiceRegistration.sales_invoice_id,
            SalesInvoice.status == "APPROVED",
        ),
        (
            "CREDIT_NOTE",
            CreditNote,
            CreditNote.credit_note_number,
            CreditNote.credit_note_date,
            CreditNote.total_amount,
            EInvoiceRegistration.credit_note_id,
            CreditNote.status == "APPROVED",
        ),
        (
            "DEBIT_NOTE",
            CustomerDebitNote,
            CustomerDebitNote.debit_note_number,
            CustomerDebitNote.debit_note_date,
            CustomerDebitNote.total_amount,
            EInvoiceRegistration.customer_debit_note_id,
            CustomerDebitNote.status == "APPROVED",
        ),
        # A completed return of billed goods is a credit note (D-TAX-2). Which
        # of them credit a bill is asked below, of the one function the
        # print and the registration ask (D-PRC-89).
        (
            "SALES_RETURN",
            SalesReturn,
            SalesReturn.return_number,
            SalesReturn.return_date,
            SalesReturn.grand_total,
            EInvoiceRegistration.sales_return_id,
            SalesReturn.status.in_(("COMPLETED", "CLOSED")),
        ),
    )
    found: list[PendingDocument] = []
    for kind, model, number, on, amount, link, issued in kinds:
        rows: Sequence[Any] = session.execute(
            select(
                model.id,
                number,
                on,
                amount,
                func.coalesce(Customer.display_name, Customer.name),
            )
            .join(Customer, Customer.id == model.customer_id)
            .where(
                model.firm_id == firm_scope,
                model.is_deleted.is_(False),
                issued,
                on >= since,
                b2b,
                ~model.id.in_(
                    select(link).where(
                        EInvoiceRegistration.firm_id == firm_scope,
                        EInvoiceRegistration.status == "REGISTERED",
                        EInvoiceRegistration.is_deleted.is_(False),
                        link.is_not(None),
                    )
                ),
            )
        ).all()
        if kind == "SALES_RETURN":
            # By either route: on a bill's own line, or off a delivery note
            # and set against the bill that charged it. A return of goods no
            # bill had charged credits no tax invoice and is not listed.
            crediting = returns_crediting_bills(session, [row[0] for row in rows])
            rows = [row for row in rows if row[0] in crediting]
        attempts = {
            getattr(row, link.key): row
            for row in session.scalars(
                select(EInvoiceRegistration).where(
                    EInvoiceRegistration.firm_id == firm_scope,
                    link.in_([row[0] for row in rows]),
                    EInvoiceRegistration.is_deleted.is_(False),
                )
            )
        }
        for doc_id, doc_number, doc_on, doc_amount, customer_name in rows:
            attempt = attempts.get(doc_id)
            deadline = doc_on + timedelta(days=REPORTING_DAYS) if binds else None
            days_left = None if deadline is None else (deadline - today).days
            found.append(
                PendingDocument(
                    document_type=kind,
                    document_id=doc_id,
                    number=doc_number,
                    on=doc_on,
                    customer_name=customer_name or "",
                    amount=doc_amount,
                    registration_status=None if attempt is None else attempt.status,
                    registration_error=(
                        None if attempt is None else attempt.error_message
                    ),
                    last_day=deadline,
                    days_left=days_left,
                    state=_state(days_left),
                )
            )
    return sorted(found, key=lambda item: (item.on, item.number))
