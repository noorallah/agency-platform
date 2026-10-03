"""Free goods for customers (BUY-1, decision A111).

Ten promotional bowls arrive at 5 each. They cannot be sold at a price.
Two given free to a customer -- who must be named -- cost promotional expense
10; one sample costs 5 more. The report shows ten received, the gifts, and
seven held.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.core.pagination import ReportWindow
from app.customers.models import Customer
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.schemas import StockWriteOffCreate
from app.inventory.services import InventoryService
from app.inventory.services.free_goods import free_goods_report
from app.products.services.free_issue import assert_not_sold_at_a_price
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm holding ten free-issue bowls at 5."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="FREEG")
    built.product.free_issue_only = True
    customer = Customer(
        firm_id=built.firm.id,
        code="CUST-FREE",
        customer_type="BUSINESS",
        name="Shop",
        display_name="Shop",
        currency_code="INR",
        status="ACTIVE",
    )
    built.session.add(customer)
    built.session.commit()
    built.customer = customer  # type: ignore[attr-defined]
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "5"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    return built


def _give(firm: _Firm, reason: str, quantity: str, *, customer: bool) -> None:
    InventoryService(firm.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=firm.branch.id,
            warehouse_id=firm.warehouse.id,
            product_id=firm.product.id,
            reason=reason,
            quantity=D(quantity),
            customer_id=firm.customer.id if customer else None,
            transaction_date=date(2026, 8, 12),
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_free_issue_goods_are_never_sold_at_a_price(firm: _Firm) -> None:
    with pytest.raises(ValidationError, match="never sold at a price"):
        assert_not_sold_at_a_price(
            firm.session, firm.firm.id, [(firm.product.id, D("12"))]
        )
    assert_not_sold_at_a_price(firm.session, firm.firm.id, [(firm.product.id, D("0"))])
    assert_not_sold_at_a_price(firm.session, firm.firm.id, [(firm.product.id, None)])


def test_giving_them_away_costs_promotional_expense(firm: _Firm) -> None:
    with pytest.raises(ValidationError, match="names the customer"):
        _give(firm, "FREE_TO_CUSTOMER", "2", customer=False)
    firm.session.rollback()
    _give(firm, "FREE_TO_CUSTOMER", "2", customer=True)
    assert firm.balance(ControlAccountPurpose.PROMOTIONAL_EXPENSE) == D("10")
    _give(firm, "SAMPLE", "1", customer=False)
    assert firm.balance(ControlAccountPurpose.PROMOTIONAL_EXPENSE) == D("15")

    rows = free_goods_report(firm.session, firm_id=firm.firm.id, window=ReportWindow())
    by_section = {(row.section, row.detail): row for row in rows}
    assert by_section[("RECEIVED", "")].quantity == D("10")
    given = by_section[("GIVEN", "Given free")]
    assert (given.party_name, given.quantity, given.value) == (
        firm.customer.display_name,
        D("2"),
        D("10"),
    )
    assert by_section[("GIVEN", "Sample")].quantity == D("1")
    assert by_section[("ON_HAND", "")].quantity == D("7")
