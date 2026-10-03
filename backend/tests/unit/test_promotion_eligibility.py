"""Offers for a customer's first order, or for one not billed in a while (SEL-6).

"10% off your first order" matches a customer with no approved bill and stops
matching once one is approved -- a draft does not count. "Come back" -- not
billed in 60 days -- matches a customer whose last approved bill is 60 days
before the document and not one billed last week.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.promotions.schemas import (
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.promotions.services import PromotionService
from app.sales_invoice.models import SalesInvoice
from tests.unit.test_promotions import (
    _firm,
    _product,
    _promotion,
    _request,
    _session_factory,
)

D = Decimal
ON = date(2026, 8, 4)
TEN = [(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})]


def _bill(
    session: Session, firm_id: UUID, customer_id: UUID, *, on: date, status: str
) -> None:
    session.add(
        SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            branch_id=uuid4(),
            invoice_number=f"SI-{uuid4().hex[:6]}",
            invoice_date=on,
            status=status,
            grand_total=D("100"),
        )
    )
    session.commit()


def _off(
    service: PromotionService, firm_id: UUID, product_id: UUID, customer_id: UUID
) -> Decimal:
    result = service.evaluate(
        _request(lines=[(1, product_id, "1", "100")], customer_id=customer_id, on=ON),
        firm_scope=firm_id,
    )
    return result.lines[0].discount_amount


def test_a_first_order_offer_stops_at_the_first_approved_bill() -> None:
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    customer_id = uuid4()
    _promotion(
        session,
        firm_id=firm.id,
        code="FIRST",
        actions=TEN,
        conditions=[
            (
                PromotionField.CUSTOMER_ORDER_COUNT,
                PromotionConditionOperator.EQUALS,
                {"value_number": D("0")},
            )
        ],
    )
    service = PromotionService(session)
    assert _off(service, firm.id, product.id, customer_id) == D("10.00")
    _bill(session, firm.id, customer_id, on=ON - timedelta(days=3), status="DRAFT")
    assert _off(service, firm.id, product.id, customer_id) == D(
        "10.00"
    ), "a draft is not an order"
    _bill(session, firm.id, customer_id, on=ON - timedelta(days=3), status="APPROVED")
    assert _off(service, firm.id, product.id, customer_id) == D("0")


def test_a_come_back_offer_needs_the_gap() -> None:
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    lapsed, regular = uuid4(), uuid4()
    _promotion(
        session,
        firm_id=firm.id,
        code="COMEBACK",
        actions=TEN,
        conditions=[
            (
                PromotionField.DAYS_SINCE_LAST_ORDER,
                PromotionConditionOperator.GREATER_OR_EQUAL,
                {"value_number": D("60")},
            )
        ],
    )
    _bill(session, firm.id, lapsed, on=ON - timedelta(days=60), status="APPROVED")
    _bill(session, firm.id, regular, on=ON - timedelta(days=7), status="CLOSED")
    service = PromotionService(session)
    assert _off(service, firm.id, product.id, lapsed) == D("10.00")
    assert _off(service, firm.id, product.id, regular) == D("0")
    assert _off(service, firm.id, product.id, uuid4()) == D(
        "0"
    ), "never billed: the order count catches that customer, not this"
