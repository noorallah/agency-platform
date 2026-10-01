"""Purchase price variance, bill line by bill line (backlog 65 row 5).

A bill charging a rate other than its receipt's posts the difference to
Purchase Price Variance; this report names the supplier, product, both rates
and the variance, so a buyer can take it up.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination.reports import ReportWindow
from app.firms.models import Firm
from app.purchase.models import PurchaseOrderLine
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_invoice.services.price_variance import PriceVarianceService
from tests.unit.test_purchase_invoice_module import (
    _bill_of,
    _branch,
    _firm,
    _purchase_order,
    _received,
    _session_factory,
    _vendor,
    _warehouse,
)

pytestmark = pytest.mark.typed_document_numbers


def _billed_at(receipt_rate: str, status: str = "APPROVED") -> tuple[Session, Firm]:
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    receipt_line.unit_price = Decimal(receipt_rate)
    session.commit()
    bill = PurchaseInvoiceService(session).create_invoice(
        _bill_of(
            receipt, receipt_line, number="SUP-9", quantity="4", on=date(2026, 8, 3)
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    bill.status = status
    session.commit()
    return session, firm


def test_a_bill_dearer_than_its_receipt_is_listed_with_the_variance() -> None:
    session, firm = _billed_at("90")

    [row] = PriceVarianceService(session).report(firm.id, ReportWindow())

    assert (row.receipt_rate, row.bill_rate, row.quantity) == (
        Decimal("90"),
        Decimal("100"),
        Decimal("4"),
    )
    assert row.variance == Decimal("40.00")
    assert row.supplier_invoice_number == "SUP-9"
    assert row.note == ""


def test_a_bill_at_the_receipt_rate_is_not_listed() -> None:
    session, firm = _billed_at("100")
    assert PriceVarianceService(session).report(firm.id, ReportWindow()) == []


def test_a_draft_bill_is_not_listed() -> None:
    session, firm = _billed_at("90", status="DRAFT")
    assert PriceVarianceService(session).report(firm.id, ReportWindow()) == []


def test_the_window_bounds_the_bills() -> None:
    session, firm = _billed_at("90")
    service = PriceVarianceService(session)
    assert service.report(firm.id, ReportWindow(from_date=date(2026, 9, 1))) == []
    assert len(service.report(firm.id, ReportWindow(to_date=date(2026, 8, 31)))) == 1


def test_one_bill_is_answered_in_any_status_for_its_own_screen() -> None:
    from app.purchase_invoice.models import PurchaseInvoice

    session, firm = _billed_at("90", status="DRAFT")
    bill_id = session.scalar(select(PurchaseInvoice.id))
    service = PriceVarianceService(session)

    [row] = service.report(firm.id, ReportWindow(), purchase_invoice_id=bill_id)

    assert row.line_number == 1
    assert row.variance == Decimal("40.00")
    assert service.report(firm.id, ReportWindow(), purchase_invoice_id=uuid4()) == []
