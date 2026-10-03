"""Formal amendment of an approved purchase order (BUY-8, decision A102).

An approved order for ten at 100 is amended to a lower price: its revision
moves to 1 and the earlier version is kept. Raising the total needs the
right to approve. Once four were received, the line cannot drop below four,
nor change product; amending it to exactly four makes it fully received. The
supplier never changes, and the print names the amendment.
"""

# ruff: noqa: D103

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import AuthorizationError, ValidationError
from app.purchase.models import PurchaseOrder
from app.purchase.schemas import PurchaseOrderAmend
from app.purchase.services import PurchaseService
from app.purchase.services.purchase_print_service import PurchaseOrderPrintService
from tests.unit.test_purchase_chain_synthesis import _Firm
from tests.unit.test_purchase_header_discount import (
    _bill_of_order,
    _order,
    _order_lines,
)

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="AMEND")


def _amendment(
    firm: _Firm, *, quantity: str, price: str, vendor_id: object = None
) -> PurchaseOrderAmend:
    return PurchaseOrderAmend.model_validate(
        {
            "branch_id": firm.branch.id,
            "warehouse_id": firm.warehouse.id,
            "vendor_id": vendor_id or firm.vendor.id,
            "purchase_date": "2026-08-02",
            "header_discount_amount": "100",
            "lines": [
                {
                    "product_id": firm.product.id,
                    "ordered_quantity": quantity,
                    "unit_price": price,
                    "discount_percent": "0",
                }
            ],
            "reason": "Supplier revised the rate",
        }
    )


def _amend(
    firm: _Firm, order: PurchaseOrder, data: PurchaseOrderAmend, *, may: bool
) -> PurchaseOrder:
    return PurchaseService(firm.session).amend_order(
        order.id,
        data,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        may_approve=may,
    )


def test_an_amendment_keeps_the_earlier_version(firm: _Firm) -> None:
    order = _order(firm, lines=[(firm.product, "10", "100")])
    before = order.grand_total
    amended = _amend(
        firm, order, _amendment(firm, quantity="10", price="90"), may=False
    )
    assert amended.revision_number == 1
    assert amended.status == "APPROVED"
    assert amended.grand_total < before
    (revision,) = PurchaseService(firm.session).list_revisions(
        order.id, firm_scope=firm.firm.id
    )
    assert revision.revision_number == 0
    assert revision.grand_total == before
    assert revision.snapshot["lines"][0]["unit_price"] == "100.0000"  # type: ignore[index]

    pdf, _ = PurchaseOrderPrintService(firm.session).render(
        order.id, firm_scope=firm.firm.id
    )
    assert pdf.startswith(b"%PDF")


def test_raising_the_total_needs_the_right_to_approve(firm: _Firm) -> None:
    order = _order(firm, lines=[(firm.product, "10", "100")])
    with pytest.raises(AuthorizationError, match="PURCHASE_APPROVE"):
        _amend(firm, order, _amendment(firm, quantity="12", price="100"), may=False)
    firm.session.rollback()
    amended = _amend(
        firm, order, _amendment(firm, quantity="12", price="100"), may=True
    )
    assert amended.revision_number == 1


def test_a_received_line_cannot_drop_below_what_came_in(firm: _Firm) -> None:
    firm.stages(order=True, receipt=False)
    order = _order(firm, lines=[(firm.product, "10", "100")])
    (line,) = _order_lines(firm, order)
    bills = firm.bills()
    bill = bills.create_invoice(
        _bill_of_order(firm, order, line, "4"),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    bills.approve_invoice(bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id)
    firm.session.refresh(order)
    assert order.status == "PARTIALLY_RECEIVED"

    with pytest.raises(ValidationError, match="4 was received"):
        _amend(firm, order, _amendment(firm, quantity="3", price="100"), may=True)
    firm.session.rollback()
    with pytest.raises(ValidationError, match="cannot change the supplier"):
        _amend(
            firm,
            order,
            _amendment(firm, quantity="4", price="100", vendor_id=firm.firm.id),
            may=True,
        )
    firm.session.rollback()
    amended = _amend(firm, order, _amendment(firm, quantity="4", price="100"), may=True)
    assert amended.status == "RECEIVED"
