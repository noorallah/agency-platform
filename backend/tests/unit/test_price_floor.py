"""Selling below cost or below a minimum price (BACKLOG 64 row 2).

The firm from ``test_sales_chain_synthesis`` holds its product at an average
cost of 60 and sells it at 100. These pin what is compared (the net rate per
stock unit, after every discount), what a message may say (the minimum, never
the cost), when it is judged (approving an order, approving a bill, once for a
counter bill), and what WARN, BLOCK and the override each do.
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.scope import ResolvedFirmScope
from app.core.exceptions import AuthorizationError, ValidationError
from app.document_framework.models import DocumentLifecycleEvent
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES
from app.inventory.models import InventoryTransaction
from app.sales_invoice.schemas import SalesInvoiceStatus
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.api.price_override import authorised_price_override
from app.sales_order.schemas import (
    PriceFloorSettingsWrite,
    SalesOrderCreate,
    SalesOrderLineWrite,
)
from app.sales_order.services import SalesOrderService
from app.sales_order.services.price_floor import PricedLine, PriceFloorService
from tests.unit.test_licence_checks import ORDER_DATE
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


class _Shop(_Firm):
    """A firm holding its product at 60 a unit, selling it at 100."""

    def __init__(self) -> None:
        """Build the firm."""
        super().__init__(_session_factory()())
        self.actor_id = uuid4()
        self.floors = PriceFloorService(self.session)

    def policy(self, enforcement: str, *, include_cost: bool = True) -> None:
        """Set the firm's price-floor policy."""
        self.floors.update_settings(
            PriceFloorSettingsWrite(
                enforcement=enforcement,  # type: ignore[arg-type]
                include_cost=include_cost,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def minimum(self, price: str | None) -> None:
        """Give the product a minimum selling price."""
        self.product.minimum_selling_price = None if price is None else Decimal(price)
        self.session.commit()

    def order(self, price: str = "100", discount_percent: str | None = None) -> UUID:
        """Raise a draft order for two units at a price."""
        row = SalesOrderService(self.session).create_order(
            SalesOrderCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                order_date=ORDER_DATE,
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=self.product.id,
                        quantity=Decimal("2"),
                        unit_price=Decimal(price),
                        discount_percent=(
                            None
                            if discount_percent is None
                            else Decimal(discount_percent)
                        ),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        return row.id

    def approve(self, order_id: UUID, reason: str | None = None) -> str:
        """Approve an order; return its status."""
        return (
            SalesOrderService(self.session)
            .approve_order(
                order_id,
                firm_scope=self.firm.id,
                actor_id=self.actor_id,
                price_override_reason=reason,
            )
            .status
        )

    def event(self, document_id: UUID) -> DocumentLifecycleEvent:
        """Return the APPROVED event on a document's timeline."""
        event = self.session.scalar(
            select(DocumentLifecycleEvent).where(
                DocumentLifecycleEvent.source_document_id == document_id,
                DocumentLifecycleEvent.action == "APPROVED",
            )
        )
        assert event is not None
        return event


@pytest.fixture
def shop() -> _Shop:
    """Build the firm."""
    return _Shop()


def test_an_unconfigured_firm_warns_and_approves(shop: _Shop) -> None:
    """No row is WARN with cost included; the order still goes through."""
    assert shop.floors.settings_response(shop.firm.id).model_dump() == {
        "enforcement": "WARN",
        "include_cost": True,
        "is_configured": False,
    }
    shop.minimum("120")
    order_id = shop.order("100")

    assert shop.approve(order_id) == "APPROVED"
    event = shop.event(order_id)
    assert event.details_json is not None
    warning = event.details_json["price_warning"]
    assert isinstance(warning, dict)
    assert event.remarks is not None
    assert "below its minimum price of 120.00" in event.remarks


def test_below_cost_never_says_what_the_cost_is(shop: _Shop) -> None:
    """Sold at 50 against a cost of 60: flagged, and 60 is nowhere in it."""
    order_id = shop.order("50")
    check = shop.floors.check(
        shop.firm.id,
        [PricedLine(1, shop.product.id, Decimal("2"), Decimal("100"))],
    )
    (finding,) = check.findings
    assert finding.floor == "cost"
    assert finding.minimum_price is None
    assert finding.net_rate == Decimal("50.00")
    assert "60" not in finding.message
    assert "below what it cost" in finding.message
    assert shop.approve(order_id) == "APPROVED"


def test_the_rate_is_judged_after_the_discount(shop: _Shop) -> None:
    """100 less 45% is 55 a unit, under the cost of 60."""
    order_id = shop.order("100", discount_percent="45")
    check = SalesOrderService(shop.session).get_order(order_id, firm_scope=shop.firm.id)
    assert check.status == "DRAFT"
    shop.policy("BLOCK")
    with pytest.raises(ValidationError, match="below what it cost"):
        shop.approve(order_id)


def test_the_higher_floor_is_the_one_named(shop: _Shop) -> None:
    """A minimum of 70 over a cost of 60: sold at 65, the minimum is named."""
    shop.minimum("70")
    check = shop.floors.check(
        shop.firm.id, [PricedLine(1, shop.product.id, Decimal("2"), Decimal("130"))]
    )
    (finding,) = check.findings
    assert finding.floor == "minimum"
    assert finding.minimum_price == Decimal("70.00")


def test_without_cost_only_the_minimum_counts(shop: _Shop) -> None:
    """A firm clearing stock below cost on purpose turns cost off."""
    shop.policy("BLOCK", include_cost=False)
    assert shop.approve(shop.order("50")) == "APPROVED"


def test_off_judges_nothing(shop: _Shop) -> None:
    """OFF finds nothing, whatever the price."""
    shop.policy("OFF")
    shop.minimum("500")
    check = shop.floors.check(
        shop.firm.id, [PricedLine(1, shop.product.id, Decimal("1"), Decimal("1"))]
    )
    assert check.findings == []
    assert check.would_block is False


def test_free_goods_are_never_judged(shop: _Shop) -> None:
    """A gift line charges no quantity, so it has no rate to be below."""
    shop.minimum("120")
    check = shop.floors.check(
        shop.firm.id, [PricedLine(2, shop.product.id, Decimal("0"), Decimal("0"))]
    )
    assert check.findings == []


def test_block_refuses_reserves_nothing_and_an_override_lets_it_through(
    shop: _Shop,
) -> None:
    """Refused before stock is held; a reason approves and is kept."""
    shop.policy("BLOCK")
    shop.minimum("120")
    order_id = shop.order("100")
    movements = len(shop.session.scalars(select(InventoryTransaction)).all())

    with pytest.raises(ValidationError, match="refuses a sale below"):
        shop.approve(order_id)
    shop.session.rollback()
    orders = SalesOrderService(shop.session)
    assert orders.get_order(order_id, firm_scope=shop.firm.id).status == "DRAFT"
    assert len(shop.session.scalars(select(InventoryTransaction)).all()) == movements

    assert shop.approve(order_id, "Clearing a damaged lot.") == "APPROVED"
    event = shop.event(order_id)
    assert event.details_json is not None
    override = event.details_json["price_override"]
    assert isinstance(override, dict)
    assert override["reason"] == "Clearing a damaged lot."
    assert event.remarks is not None
    assert event.remarks.startswith("Price floor overridden")


def test_a_counter_bill_is_judged_once_at_its_own_approval(shop: _Shop) -> None:
    """The order the bill raises is not judged; the bill is."""
    shop.stages(quotation=False, sales_order=False, delivery_note=False)
    shop.policy("BLOCK")
    shop.minimum("150")
    bills = SalesInvoiceService(shop.session)
    draft = bills.create_invoice(
        shop.bare_bill(), firm_id=shop.firm.id, actor_id=shop.actor_id
    )
    with pytest.raises(ValidationError, match="minimum price of 150.00") as refused:
        bills.approve_invoice(draft.id, firm_scope=shop.firm.id, actor_id=shop.actor_id)
    assert str(refused.value).count("Line 1") == 1
    shop.session.rollback()

    approved = bills.approve_invoice(
        draft.id,
        firm_scope=shop.firm.id,
        actor_id=shop.actor_id,
        price_override_reason="Matching a competitor, agreed by the owner.",
    )
    assert approved.status == SalesInvoiceStatus.APPROVED.value


def test_settings_are_audited_and_marked_configured(shop: _Shop) -> None:
    """The first write creates the row; the response says the firm chose."""
    shop.policy("BLOCK", include_cost=False)
    assert shop.floors.settings_response(shop.firm.id).model_dump() == {
        "enforcement": "BLOCK",
        "include_cost": False,
        "is_configured": True,
    }


def test_only_the_override_permission_may_give_a_reason() -> None:
    """A reason from someone without the permission is refused, not ignored."""

    def scope(*codes: str) -> ResolvedFirmScope:
        """Build a scope whose principal holds the given codes."""
        principal = SimpleNamespace(has_permission=lambda code: code in codes)
        return ResolvedFirmScope(principal=principal, firm_id=uuid4())  # type: ignore[arg-type]

    assert authorised_price_override(scope(), None) is None
    assert authorised_price_override(scope(), "  ") is None
    with pytest.raises(AuthorizationError):
        authorised_price_override(scope(), "because")
    assert (
        authorised_price_override(scope("SALES_PRICE_OVERRIDE"), " because ")
        == "because"
    )


def test_the_role_the_floor_constrains_cannot_lift_it() -> None:
    """Seeded, held by firm administrators, withheld from sales managers."""
    assert "SALES_PRICE_OVERRIDE" in SYSTEM_PERMISSION_CODES
    assert "SALES_PRICE_OVERRIDE" in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "SALES_PRICE_OVERRIDE" not in ROLE_PERMISSION_CODES["SALES_MANAGER"]
    assert "SALES_PRICE_OVERRIDE" not in ROLE_PERMISSION_CODES["SALES_EXECUTIVE"]
