"""Claims to the principal (SEL-11, decision A128).

The firm holds ten units at 100 of a product whose brand belongs to the
principal ACME, which is also its supplier. In August a customer was billed
an order ACME's scheme took 200 off (ACME bears 50%), one unit expired on the
shelf (100),
and a customer returned two units broken out of four, credited at 150 each
before tax. The claim is 100 + 100 + 300 = 500; it books Dr claims
receivable 500, Cr promotional expense 100 and inventory adjustment 400.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import FirmControlAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from app.inventory.schemas.inventory import StockWriteOffCreate
from app.inventory.services.inventory_service import InventoryService
from app.principal_claims.services import (
    PrincipalClaimReceiptWrite,
    PrincipalClaimService,
    PrincipalClaimWrite,
)
from app.products.models.brand import Brand, Principal
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.models import SalesReturn, SalesReturnLine
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


@pytest.fixture
def firm() -> _Firm:
    """Build the firm, ACME's brand on its product, and August's three losses."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="CLAIM")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    session = built.session
    principal = Principal(
        firm_id=built.firm.id, code="ACME", name="Acme Ltd", vendor_id=built.vendor.id
    )
    session.add(principal)
    session.flush()
    brand = Brand(firm_id=built.firm.id, name="Acme", principal_id=principal.id)
    session.add(brand)
    session.flush()
    built.product.brand_id = brand.id
    scheme = Promotion(
        firm_id=built.firm.id,
        code="ACME-AUG",
        name="Acme August scheme",
        priority=10,
        status="ACTIVE",
        version_group_id=uuid4(),
        principal_id=principal.id,
        principal_share_percent=D("50"),
    )
    session.add(scheme)
    session.flush()
    # The order the scheme took 200 off, billed whole on the 5th: a claim
    # reads what the bills passed on, never the order's claim alone.
    order = SalesOrder(
        firm_id=built.firm.id,
        customer_id=uuid4(),
        branch_id=built.branch.id,
        warehouse_id=built.warehouse.id,
        order_number="SO-77",
        order_date=date(2026, 8, 5),
        status="APPROVED",
    )
    sale = SalesInvoice(
        firm_id=built.firm.id,
        customer_id=order.customer_id,
        branch_id=built.branch.id,
        invoice_number="SI-77",
        invoice_date=date(2026, 8, 5),
        status="APPROVED",
    )
    session.add_all([order, sale])
    session.flush()
    ordered = SalesOrderLine(
        sales_order_id=order.id,
        firm_id=built.firm.id,
        line_number=1,
        product_id=built.product.id,
        quantity=D("2"),
        unit_price=D("1000"),
        gross_amount=D("2000"),
        discount_amount=D("200"),
        discount_source="promotion",
    )
    session.add(ordered)
    session.flush()
    session.add(
        SalesInvoiceLine(
            sales_invoice_id=sale.id,
            firm_id=built.firm.id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=order.id,
            source_document_number=order.order_number,
            source_document_line_id=ordered.id,
            source_document_line_number=1,
            product_id=built.product.id,
            delivered_quantity=D("2"),
            current_invoice_quantity=D("2"),
            unit_price=D("1000"),
            gross_amount=D("2000"),
            discount_amount=D("200"),
        )
    )
    session.add(
        PromotionRedemption(
            firm_id=built.firm.id,
            promotion_id=scheme.id,
            document_type="SALES_ORDER",
            document_id=order.id,
            document_number="SO-77",
            redeemed_on=date(2026, 8, 5),
            benefit_amount=D("200"),
            status="CLAIMED",
        )
    )
    returned = SalesReturn(
        firm_id=built.firm.id,
        customer_id=uuid4(),
        branch_id=built.branch.id,
        warehouse_id=built.warehouse.id,
        return_number="SR-9",
        return_date=date(2026, 8, 20),
        status="COMPLETED",
    )
    session.add(returned)
    session.flush()
    session.add(
        SalesReturnLine(
            sales_return_id=returned.id,
            firm_id=built.firm.id,
            line_number=1,
            source_document_type="SALES_INVOICE",
            source_document_id=uuid4(),
            source_document_number="SI-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=built.product.id,
            current_return_quantity=D("4"),
            restock_quantity=D("2"),
            damaged_quantity=D("1"),
            scrap_quantity=D("1"),
            unit_price=D("150"),
            gross_amount=D("600"),
            discount_amount=D("0"),
            net_amount=D("708"),
        )
    )
    session.commit()
    InventoryService(session).write_off_stock(
        StockWriteOffCreate(
            branch_id=built.branch.id,
            warehouse_id=built.warehouse.id,
            product_id=built.product.id,
            reason="EXPIRY",
            quantity=D("1"),
            transaction_date=date(2026, 8, 10),
        ),
        firm_scope=built.firm.id,
        actor_id=built.actor_id,
    )
    built.principal = principal  # type: ignore[attr-defined]
    return built


def _write(firm: _Firm) -> PrincipalClaimWrite:
    return PrincipalClaimWrite(
        principal_id=firm.principal.id,  # type: ignore[attr-defined]
        period_from=AUGUST[0],
        period_to=AUGUST[1],
        claim_date=date(2026, 9, 2),
    )


def test_a_claim_gathers_schemes_expiry_and_breakage_and_books_them(
    firm: _Firm,
) -> None:
    service = PrincipalClaimService(firm.session)
    preview = service.preview(_write(firm), firm_id=firm.firm.id)
    assert (
        preview.scheme_amount,
        preview.expiry_amount,
        preview.breakage_amount,
        preview.total_amount,
    ) == (D("100.00"), D("100.00"), D("300.00"), D("500.00"))

    claim = service.raise_claim(
        _write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    (view,) = service.responses([claim])
    assert (view.status, view.outstanding, len(view.lines)) == (
        "RAISED",
        D("500.00"),
        3,
    )
    assert firm.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == D("500")
    assert firm.balance(ControlAccountPurpose.PROMOTIONAL_EXPENSE) == D("-100")
    # The expiry write-off charged 100 here; the claim gives back 400.
    assert firm.balance(ControlAccountPurpose.INVENTORY_ADJUSTMENT) == D("-300")

    with pytest.raises(ValidationError, match="Nothing is left to claim"):
        service.raise_claim(_write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id)


def test_a_payment_settles_part_and_a_settled_claim_cannot_be_cancelled(
    firm: _Firm,
) -> None:
    service = PrincipalClaimService(firm.session)
    claim = service.raise_claim(
        _write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    bank = firm.session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == firm.firm.id,
            FirmControlAccount.purpose == ControlAccountPurpose.BANK.value,
        )
    )
    assert bank is not None
    with pytest.raises(ValidationError, match="still to settle"):
        service.record_receipt(
            claim.id,
            PrincipalClaimReceiptWrite(
                received_on=date(2026, 9, 10), amount=D("600"), money_account_id=bank
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    service.record_receipt(
        claim.id,
        PrincipalClaimReceiptWrite(
            received_on=date(2026, 9, 10), amount=D("200"), money_account_id=bank
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (view,) = service.responses([claim])
    assert (view.status, view.settled_by_payment, view.outstanding) == (
        "PART_SETTLED",
        D("200.00"),
        D("300.00"),
    )
    assert firm.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == D("300")
    with pytest.raises(ValidationError, match="Part of this claim is settled"):
        service.cancel(claim.id, "Wrong", firm_id=firm.firm.id, actor_id=firm.actor_id)

    service.reverse_receipt(
        claim.id,
        view.receipts[0].id,
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    service.cancel(claim.id, "Wrong", firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert firm.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == D("0")
    # Cancelling frees the sources to be claimed again.
    again = service.raise_claim(
        _write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert again.total_amount == D("500.00")


def test_a_credit_note_settles_the_claim_against_the_supplier_s_bills(
    firm: _Firm,
) -> None:
    from app.party_adjustments.schemas import PartyAdjustmentCreate
    from app.party_adjustments.services import PartyAdjustmentService

    service = PrincipalClaimService(firm.session)
    claim = service.raise_claim(
        _write(firm), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    adjustments = PartyAdjustmentService(firm.session)
    note = adjustments.create(
        PartyAdjustmentCreate(
            kind="PRINCIPAL_CLAIM",
            adjustment_date=date(2026, 9, 12),
            vendor_id=firm.vendor.id,
            amount=D("500"),
            reason="Acme credit note CN-55",
            principal_claim_id=claim.id,
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    adjustments.approve(
        note.id,
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
        may_approve_above_threshold=True,
    )
    (view,) = service.responses([claim])
    assert (view.status, view.settled_by_credit_note, view.outstanding) == (
        "SETTLED",
        D("500.00"),
        D("0.00"),
    )
    assert firm.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == D("0")


def test_a_period_that_runs_backwards_is_refused() -> None:
    with pytest.raises(ValueError, match="ends before it starts"):
        PrincipalClaimWrite(
            principal_id=uuid4(),
            period_from=date(2026, 8, 31),
            period_to=date(2026, 8, 1),
            claim_date=date(2026, 9, 1),
        )
