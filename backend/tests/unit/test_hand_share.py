"""Share a bill on WhatsApp by hand (MSG-1, §51 A2).

The server says whom to send to and what to say, needing no messaging account,
no switch and no opt-in -- the person sends from their own WhatsApp. The share
goes on the bill's timeline as *shared by hand*, never as *sent*.
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.document_framework.models import DocumentPrintTemplate
from app.messaging.api.router import prepare_hand_share, record_hand_share
from app.messaging.schemas import HandShareRecord
from app.messaging.services.hand_share import HandShareService, whatsapp_number
from app.sales_invoice.services import SalesInvoiceService
from tests.unit.test_messaging import _scope, _Shop


@pytest.fixture
def shop() -> _Shop:
    """Build the firm; messaging is left off, as most firms have it."""
    return _Shop()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("+91 98765-43210", "919876543210"),
        ("98765 43210", "919876543210"),
        ("098765 43210", "919876543210"),
        ("+971 50 123 4567", "971501234567"),
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_a_number_is_written_as_wa_me_wants_it(
    typed: str | None, expected: str | None
) -> None:
    assert whatsapp_number(typed) == expected


def test_an_approved_bill_names_the_number_and_the_message(shop: _Shop) -> None:
    bill = shop.approved_bill()

    share = prepare_hand_share(
        bill.id, _scope(shop.firm.id, shop.actor_id), shop.session
    ).data

    assert share is not None
    assert share.phone == "+919876543210"
    assert share.whatsapp_number == "919876543210"
    assert bill.invoice_number in share.text
    assert f"{bill.grand_total:,.2f}" in share.text
    assert share.file_name == f"{bill.invoice_number.replace('/', '-')}.pdf"


def test_no_account_switch_or_opt_in_is_needed(shop: _Shop) -> None:
    """Messaging is off and the customer never opted in: sharing still works."""
    shop.customer.whatsapp_opt_in = False
    shop.session.commit()
    bill = shop.approved_bill()

    share = HandShareService(shop.session).prepare(bill.id, firm_id=shop.firm.id)

    assert share.whatsapp_number == "919876543210"


def test_a_customer_with_no_number_lets_whatsapp_ask(shop: _Shop) -> None:
    shop.customer.phone = None
    shop.session.commit()
    bill = shop.approved_bill()

    share = HandShareService(shop.session).prepare(bill.id, firm_id=shop.firm.id)

    assert share.phone is None
    assert share.whatsapp_number is None


def test_the_upi_id_is_offered_while_the_bill_owes_money(shop: _Shop) -> None:
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
    bill = shop.approved_bill()

    share = HandShareService(shop.session).prepare(bill.id, firm_id=shop.firm.id)

    assert f"Pay {bill.grand_total:,.2f} by UPI to sriram@okaxis." in share.text


def test_a_draft_is_not_shared(shop: _Shop) -> None:
    draft = SalesInvoiceService(shop.session).create_invoice(
        shop.bare_bill(), firm_id=shop.firm.id, actor_id=shop.actor_id
    )

    with pytest.raises(ValidationError, match="Only an approved invoice"):
        HandShareService(shop.session).prepare(draft.id, firm_id=shop.firm.id)


def test_the_share_goes_on_the_timeline_as_shared_by_hand(shop: _Shop) -> None:
    bill = shop.approved_bill()

    record_hand_share(
        HandShareRecord(document_id=bill.id, recipient="+919876543210"),
        _scope(shop.firm.id, shop.actor_id),
        shop.session,
    )

    lines = shop.timeline(bill.id)
    assert [(line.action, line.remarks) for line in lines] == [
        ("MESSAGE_SHARED", "WhatsApp shared by hand to +919876543210")
    ]
    # Nothing was queued: the firm's account sent nothing.
    assert shop.outbox() == []


def test_another_firms_bill_is_not_found(shop: _Shop) -> None:
    bill = shop.approved_bill()

    with pytest.raises(ResourceNotFoundError):
        HandShareService(shop.session).prepare(bill.id, firm_id=uuid4())
