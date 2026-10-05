"""Free goods given on a bill reach the claim to the principal.

A claim counted a scheme's discount, expired stock and breakage. Goods
given free -- the "10 + 1" a salesman types on a line, or the free units an
offer adds -- were dispatched, cost the firm what they cost, and were claimed
from nobody: an offer's free goods are worth nothing in `benefit_amount`, and
a typed free quantity was no source at all.

The firm here holds stock at a cost of 60 and bills at 100. In August:

* a bill of 4 with **1 typed free** of ACME's product: cost 60, claimed in
  full as its own source, FREE_GOODS;
* a bill of 4 under ACME's "2 + 1" offer, of which ACME bears half: 2 free,
  cost 120, 60 claimed under SCHEME beside the scheme's money;
* typed free goods of a product that is nobody's, of a product with no cost,
  and on a bill never approved: nothing.

The claim is 60 + 60 = 120: Dr claims receivable, Cr cost of goods sold,
where the dispatch put the cost. Every case runs on a request-shaped session.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.finance.models import FirmControlAccount, GLPosting
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.models import ProductValuation
from app.inventory.schemas.inventory import InventoryAdjustmentCreate
from app.inventory.services.inventory_service import InventoryService
from app.principal_claims.services import PrincipalClaimService, PrincipalClaimWrite
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.promotions.models import Promotion, PromotionAction
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_return.models import SalesReturn, SalesReturnLine
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

D = Decimal
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


class _Agency:
    """A counter-selling firm that carries ACME's product among others."""

    def __init__(self) -> None:
        """Build the firm, the principal, its brand and its half-funded offer."""
        self.session: Session = _request_session()
        self.setup = _Firm(self.session)
        self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.firm_id: UUID = self.setup.firm.id
        self.actor = uuid4()
        self.principal = Principal(firm_id=self.firm_id, code="ACME", name="Acme Ltd")
        self.session.add(self.principal)
        self.session.flush()
        brand = Brand(firm_id=self.firm_id, name="Acme", principal_id=self.principal.id)
        self.session.add(brand)
        self.session.flush()
        self.brand_id: UUID = brand.id
        self.setup.product.brand_id = brand.id
        self.session.commit()
        self.bills = SalesInvoiceService(self.session)

    def offer(self) -> Promotion:
        """Publish ACME's "buy 2, get 1 free", of which ACME bears half."""
        row = Promotion(
            firm_id=self.firm_id,
            code="ACME-2PLUS1",
            name="Acme 2 + 1",
            priority=10,
            status="ACTIVE",
            version_group_id=uuid4(),
            version_number=1,
            principal_id=self.principal.id,
            principal_share_percent=D("50"),
        )
        self.session.add(row)
        self.session.flush()
        self.session.add(
            PromotionAction(
                firm_id=self.firm_id,
                promotion_id=row.id,
                sequence=1,
                action_type="FREE_QUANTITY",
                parameters={"buy_quantity": "2", "free_quantity": "1"},
            )
        )
        self.session.commit()
        return row

    def product(self, code: str, *, cost: str | None, acme: bool) -> Product:
        """Add a product with ten in stock, costed or not, ACME's or not."""
        row = Product(
            firm_id=self.firm_id,
            code=code,
            name=f"Product {code}",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            brand_id=self.brand_id if acme else None,
        )
        self.session.add(row)
        self.session.commit()
        InventoryService(self.session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.setup.branch.id,
                warehouse_id=self.setup.warehouse.id,
                product_id=row.id,
                quantity=D("10"),
                reference_number=f"ADJ-{code}",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 1),
            ),
            firm_scope=self.firm_id,
            actor_id=self.actor,
        )
        if cost is not None:
            # An adjustment carries no price, so the cost is given the way
            # the shared firm gives its own opening stock one.
            valuation = self.session.scalars(
                select(ProductValuation).where(
                    ProductValuation.firm_id == self.firm_id,
                    ProductValuation.product_id == row.id,
                )
            ).one()
            valuation.average_cost = D(cost)
            valuation.total_value = valuation.quantity_on_hand * D(cost)
            self.session.commit()
        return row

    def bill(
        self,
        *,
        free: str | None,
        product: Product | None = None,
        approve: bool = True,
    ) -> SalesInvoice:
        """Bill four at 100, with a typed free quantity or none."""
        invoice = self.bills.create_invoice(
            SalesInvoiceCreate(
                customer_id=self.setup.customer.id,
                invoice_date=date(2026, 8, 4),
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=(product or self.setup.product).id,
                        line_number=1,
                        current_invoice_quantity=D("4"),
                        free_quantity=None if free is None else D(free),
                        unit_price=D("100"),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        if approve:
            self.bills.approve_invoice(
                invoice.id, firm_scope=self.firm_id, actor_id=self.actor
            )
        return invoice

    def write(self, kinds: list[str] | None = None) -> PrincipalClaimWrite:
        """Describe August's claim on ACME."""
        return PrincipalClaimWrite(
            principal_id=self.principal.id,
            period_from=AUGUST[0],
            period_to=AUGUST[1],
            claim_date=date(2026, 9, 2),
            **({} if kinds is None else {"kinds": kinds}),
        )

    def balance(self, purpose: ControlAccountPurpose) -> Decimal:
        """Debit less credit on the firm's account for one purpose."""
        total = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            )
            .select_from(GLPosting)
            .join(
                FirmControlAccount,
                FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
            )
            .where(
                FirmControlAccount.firm_id == self.firm_id,
                FirmControlAccount.purpose == purpose.value,
                FirmControlAccount.is_deleted.is_(False),
                GLPosting.is_deleted.is_(False),
            )
        )
        return D(str(total or 0))


def _august() -> _Agency:
    """Return the agency after August's five bills."""
    agency = _Agency()
    agency.bill(free="1")
    agency.offer()
    agency.bill(free=None)
    agency.bill(free="1", product=agency.product("OTHER-1", cost="60", acme=False))
    agency.bill(free="1", product=agency.product("NOCOST-1", cost=None, acme=True))
    agency.bill(free="1", approve=False)
    return agency


def test_typed_and_offer_free_goods_are_claimed_at_cost_each_as_its_own() -> None:
    """Typed free goods in full, an offer's at the principal's share."""
    agency = _august()
    service = PrincipalClaimService(agency.session)

    preview = service.preview(agency.write(), firm_id=agency.firm_id)

    assert (
        preview.scheme_amount,
        preview.free_goods_amount,
        preview.expiry_amount,
        preview.breakage_amount,
        preview.total_amount,
    ) == (D("60.00"), D("60.00"), D("0"), D("0"), D("120.00"))
    assert [
        (line.kind, line.product_name, line.quantity, line.description, line.amount)
        for line in preview.lines
    ] == [
        (
            "SCHEME",
            "Product SKU-001",
            D("2.0000"),
            "Free goods under Acme 2 + 1",
            D("60.00"),
        ),
        (
            "FREE_GOODS",
            "Product SKU-001",
            D("1.0000"),
            "Free goods given on the bill",
            D("60.00"),
        ),
    ]
    assert all(line.source_number for line in preview.lines)


def test_the_claim_gives_the_cost_back_where_the_dispatch_put_it() -> None:
    """Dr claims receivable, Cr cost of goods sold; then nothing is left."""
    agency = _august()
    service = PrincipalClaimService(agency.session)
    sold_at = agency.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD)

    claim = service.raise_claim(
        agency.write(), firm_id=agency.firm_id, actor_id=agency.actor
    )

    (view,) = service.responses([claim])
    assert (view.scheme_amount, view.free_goods_amount, view.total_amount) == (
        D("60.00"),
        D("60.00"),
        D("120.00"),
    )
    assert (view.status, view.outstanding, len(view.lines)) == (
        "RAISED",
        D("120.00"),
        2,
    )
    assert agency.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == D("120")
    assert agency.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD) == sold_at - D(
        "120"
    )
    assert agency.balance(ControlAccountPurpose.PROMOTIONAL_EXPENSE) == D("0")

    with pytest.raises(ValidationError, match="Nothing is left to claim"):
        service.raise_claim(
            agency.write(), firm_id=agency.firm_id, actor_id=agency.actor
        )
    agency.session.rollback()

    # Cancelling gives the cost back to the books and frees both sources.
    service.cancel(
        claim.id, "raised early", firm_id=agency.firm_id, actor_id=agency.actor
    )
    assert agency.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD) == sold_at
    again = service.preview(agency.write(), firm_id=agency.firm_id)
    assert again.total_amount == D("120.00")


def test_typed_free_goods_can_be_claimed_or_left_out_on_their_own() -> None:
    """`kinds` names the new source like the other three."""
    agency = _august()
    service = PrincipalClaimService(agency.session)

    only = service.preview(agency.write(["FREE_GOODS"]), firm_id=agency.firm_id)
    without = service.preview(
        agency.write(["SCHEME", "EXPIRY", "BREAKAGE"]), firm_id=agency.firm_id
    )

    assert [line.kind for line in only.lines] == ["FREE_GOODS"]
    assert (only.free_goods_amount, only.total_amount) == (D("60.00"), D("60.00"))
    assert [line.kind for line in without.lines] == ["SCHEME"]
    assert without.free_goods_amount == D("0")


def test_a_return_of_what_was_charged_leaves_the_free_goods_claimed() -> None:
    """A return takes back charged units only; the free one stayed given."""
    agency = _Agency()
    bill = agency.bill(free="1")
    returned = SalesReturn(
        firm_id=agency.firm_id,
        customer_id=agency.setup.customer.id,
        branch_id=agency.setup.branch.id,
        warehouse_id=agency.setup.warehouse.id,
        return_number="SR-1",
        return_date=date(2026, 8, 20),
        status="COMPLETED",
    )
    agency.session.add(returned)
    agency.session.flush()
    agency.session.add(
        SalesReturnLine(
            sales_return_id=returned.id,
            firm_id=agency.firm_id,
            line_number=1,
            source_document_type="SALES_INVOICE",
            source_document_id=bill.id,
            source_document_number=bill.invoice_number,
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=agency.setup.product.id,
            current_return_quantity=D("4"),
            restock_quantity=D("4"),
            unit_price=D("100"),
            gross_amount=D("400"),
            discount_amount=D("0"),
            net_amount=D("400"),
        )
    )
    agency.session.commit()

    preview = PrincipalClaimService(agency.session).preview(
        agency.write(), firm_id=agency.firm_id
    )

    assert (preview.free_goods_amount, preview.breakage_amount) == (
        D("60.00"),
        D("0"),
    )


def test_an_order_line_says_which_offer_gave_its_free_goods() -> None:
    """Typed is null; an offer's free goods name the offer on the line."""
    agency = _Agency()
    offer = agency.offer()
    agency.bill(free="1")
    agency.bill(free=None)
    agency.session.expire_all()

    given = {
        line.free_quantity: line.free_promotion_id
        for line in agency.session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.is_deleted.is_(False))
        )
    }
    assert given == {D("1.0000"): None, D("2.0000"): offer.id}

    order = agency.session.scalars(
        select(SalesOrder).order_by(SalesOrder.created_at.desc())
    ).first()
    assert order is not None
    shown = SalesOrderService(agency.session).order_response(order)
    assert {line.free_promotion_id for line in shown.lines} <= {None, offer.id}
