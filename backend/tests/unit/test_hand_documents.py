"""Sending documents other than the invoice by hand (MSG-4, decision A95).

A statement, a receipt, an order confirmation, a quotation and a purchase
order go by email with their own PDF and a covering note naming them. They do
not go on WhatsApp or SMS from the firm's account, a reversed receipt is not
sent as proof of payment, and the sales order and receipt now print.
"""

# ruff: noqa: D103, F811

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.messaging.schemas import ManualSendRequest
from app.messaging.services.hand_documents import render_attachment
from app.sales_order.models import SalesOrder
from app.sales_order.services.order_print_service import SalesOrderPrintService
from app.settlements.services.receipt_print import ReceiptPrintService
from tests.unit.test_messaging import _fakes, _Shop, shop  # noqa: F401


def test_a_statement_goes_by_email_with_its_covering_note(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("EMAIL")
    row = shop.messaging.send_document(
        ManualSendRequest(
            document_type="CUSTOMER_STATEMENT",
            document_id=shop.customer.id,
            channel="EMAIL",
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    assert row.recipient == "buyer@example.com"
    assert row.attach_pdf is True
    assert row.subject is not None and row.subject.startswith("Statement of account")
    assert "Please find attached our statement of account" in (row.body or "")

    pdf = render_attachment(
        shop.session,
        firm_id=shop.firm.id,
        document_type="CUSTOMER_STATEMENT",
        document_id=shop.customer.id,
        on=utc_now().date(),
    )
    assert pdf is not None and pdf[0].startswith(b"%PDF")


def test_only_the_invoice_goes_on_whatsapp(shop: _Shop) -> None:
    shop.switch_on()
    shop.channel("SMS")
    with pytest.raises(ValidationError, match="email this one"):
        shop.messaging.send_document(
            ManualSendRequest(
                document_type="CUSTOMER_STATEMENT",
                document_id=shop.customer.id,
                channel="SMS",
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )


def test_the_order_and_the_receipt_print(shop: _Shop) -> None:
    from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
    from app.settlements.services import ReceiptService

    bill = shop.approved_bill()
    order = shop.session.query(SalesOrder).first()
    assert order is not None, "a counter bill raises its own order"
    pdf, name = SalesOrderPrintService(shop.session).render(
        order.id, firm_scope=shop.firm.id
    )
    assert pdf.startswith(b"%PDF") and name.endswith(".pdf")

    receipt = ReceiptService(shop.session).create(
        SettlementCreate(
            party_id=shop.customer.id,
            settlement_date=bill.invoice_date,
            amount=Decimal("10"),
            method=SettlementMethodEnum.CASH,
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor_id,
    )
    shop.session.commit()
    voucher, _ = ReceiptPrintService(shop.session).render(
        receipt.id, firm_scope=shop.firm.id
    )
    assert voucher.startswith(b"%PDF")

    receipt.status = "REVERSED"
    shop.session.commit()
    shop.switch_on()
    shop.channel("EMAIL")
    with pytest.raises(ValidationError, match="proof of payment"):
        shop.messaging.send_document(
            ManualSendRequest(
                document_type="RECEIPT", document_id=receipt.id, channel="EMAIL"
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor_id,
        )
