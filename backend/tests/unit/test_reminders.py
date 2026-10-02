"""Payment reminders a person sends (MSG-3, §51 A4).

*Remind* sends the customer their statement of account -- the movement, the
balance and the bills still unpaid -- by email through the firm's account, or
from the person's own WhatsApp. A customer marked *no reminders* gets none by
either road, and a customer who owes nothing is not reminded.
"""

# ruff: noqa: D103

from datetime import date

import pytest

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.customers.services import statement_pdf
from app.customers.services.statement_pdf import CustomerStatementPdfService
from app.document_framework.models import DocumentPrintTemplate
from app.messaging.api.router import (
    prepare_reminder_share,
    record_hand_share,
    remind_customer,
)
from app.messaging.schemas import HandShareRecord, ReminderRequest
from app.messaging.services.outbox_worker import _attachments as real_attachments
from app.messaging.services.reminders import ReminderService
from app.sales_invoice.services.invoice_pdf import PartyBlock
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_messaging import _fakes, _overdue, _scope, _Shop

__all__ = ["_fakes"]


@pytest.fixture
def shop(monkeypatch: pytest.MonkeyPatch) -> _Shop:
    """Build the firm, naming the seller without the platform store."""
    monkeypatch.setattr(
        statement_pdf,
        "firm_party",
        lambda firm_id: PartyBlock(name="Sri Ram & Sons", address_lines=[]),
    )
    return _Shop()


def _remind(shop: _Shop, **values: object) -> object:
    return remind_customer(
        ReminderRequest(customer_id=shop.customer.id, **values),  # type: ignore[arg-type]
        _scope(shop.firm.id, shop.actor_id),
        shop.session,
    ).data


# -- The statement on paper ------------------------------------------------------


def test_the_statement_names_the_balance_and_each_unpaid_bill(shop: _Shop) -> None:
    bill = _overdue(shop, 10)

    pdf, name = CustomerStatementPdfService(shop.session).render(
        shop.customer.id, firm_id=shop.firm.id, to_date=date(2026, 10, 3)
    )
    text = _text_of(pdf).replace(" | ", " ")

    assert name == f"statement-{shop.customer.code}-2026-10-03.pdf"
    assert "STATEMENT OF ACCOUNT" in text
    assert "BILLS UNPAID" in text
    assert bill.invoice_number in text
    assert f"{bill.grand_total:,.2f}" in text
    assert "past due" in text


def test_the_statement_offers_the_firms_upi_id(shop: _Shop) -> None:
    shop.session.add(
        DocumentPrintTemplate(
            firm_id=shop.firm.id,
            document_type="SALES_INVOICE",
            upi_id="sriram@okaxis",
            created_by=shop.actor_id,
            updated_by=shop.actor_id,
        )
    )
    shop.session.commit()
    _overdue(shop, 10)

    pdf, _ = CustomerStatementPdfService(shop.session).render(
        shop.customer.id, firm_id=shop.firm.id
    )

    assert "You may pay by UPI to sriram@okaxis." in _text_of(pdf).replace(" | ", "")


# -- By email --------------------------------------------------------------------


def test_remind_queues_the_statement_by_email(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("EMAIL")
    bill = _overdue(shop, 10)

    message = _remind(shop)

    (row,) = shop.outbox()
    assert message is not None
    assert (row.event_code, row.document_type, row.document_id) == (
        "MANUAL_REMINDER",
        "CUSTOMER_STATEMENT",
        shop.customer.id,
    )
    assert row.status == "QUEUED"
    assert row.recipient == "buyer@example.com"
    assert row.attach_pdf is True
    assert bill.invoice_number in (row.body or "")
    assert "Statement of account" in (row.subject or "")


def test_the_email_attaches_the_statement(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("EMAIL")
    _overdue(shop, 10)
    _remind(shop)
    (row,) = shop.outbox()

    (attachment,) = real_attachments(shop.session, row)

    assert attachment.filename.startswith(f"statement-{shop.customer.code}-")
    assert attachment.content.startswith(b"%PDF")


def test_no_reminders_means_none_by_email(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("EMAIL")
    shop.customer.no_reminders = True
    shop.session.commit()
    _overdue(shop, 10)

    with pytest.raises(ValidationError, match="asked for no reminders"):
        _remind(shop)
    assert shop.outbox() == []


def test_a_customer_who_owes_nothing_is_not_reminded(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("EMAIL")

    with pytest.raises(ValidationError, match="owes nothing"):
        _remind(shop)


def test_email_needs_messaging_on(shop: _Shop) -> None:
    _overdue(shop, 10)

    with pytest.raises(ValidationError, match="Messaging is off"):
        _remind(shop)


# -- On WhatsApp, by hand --------------------------------------------------------


def test_whatsapp_by_hand_needs_no_account(shop: _Shop) -> None:
    bill = _overdue(shop, 10)

    share = prepare_reminder_share(
        shop.customer.id, _scope(shop.firm.id, shop.actor_id), shop.session
    ).data

    assert share is not None
    assert share.document_type == "CUSTOMER_STATEMENT"
    assert share.whatsapp_number == "919876543210"
    assert bill.invoice_number in share.text
    assert share.file_name.startswith(f"statement-{shop.customer.code}-")


def test_no_reminders_means_none_on_whatsapp_either(shop: _Shop) -> None:
    shop.customer.no_reminders = True
    shop.session.commit()
    _overdue(shop, 10)

    with pytest.raises(ValidationError, match="asked for no reminders"):
        ReminderService(shop.session).prepare_whatsapp(
            shop.customer.id, firm_id=shop.firm.id
        )


def test_a_reminder_shared_by_hand_is_in_the_customers_trail(shop: _Shop) -> None:
    _overdue(shop, 10)

    record_hand_share(
        HandShareRecord(
            document_type="CUSTOMER_STATEMENT",
            document_id=shop.customer.id,
            recipient="+919876543210",
        ),
        _scope(shop.firm.id, shop.actor_id),
        shop.session,
    )

    entries = [
        row
        for row in shop.session.query(AuditLog).all()
        if row.action == "message.reminder_shared_by_hand"
    ]
    assert len(entries) == 1
    assert entries[0].entity_id == shop.customer.id
