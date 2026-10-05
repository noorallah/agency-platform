"""A counter bill claims its offer when the bill is approved (D-SELL-85).

A claim on an offer is counted at approval, under a lock, never while a
document is priced. A counter bill raises a sales order nobody typed and
approves it at every *save*, and the claim was made there: a draft, a held
bill and every edit held a live claim, so unapproved bills could use up an
offer limited to a few. The order's claims now stay PENDING until the bill
itself is approved.

Every case runs on a request-shaped session (autoflush off).
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.services.report_service import PromotionReportService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from tests.unit.test_sales_chain_synthesis import (
    _coupon_offer,
    _Firm,
    _request_session,
    _sent_back,
)


def _counter(limit: int | None = 1) -> tuple[Session, _Firm, SalesInvoiceService]:
    """Return a firm that types only the bill, with a coupon offer of a limit."""
    session = _request_session()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    _coupon_offer(setup)
    offer = session.scalars(select(Promotion)).one()
    offer.max_redemptions = limit
    session.commit()
    return session, setup, SalesInvoiceService(session)


def _draft(
    setup: _Firm, service: SalesInvoiceService, *, coupon: str | None = "SAVE10"
) -> SalesInvoice:
    """Save a draft counter bill of 4 at 100, with or without the coupon."""
    return service.create_invoice(
        setup.bare_bill().model_copy(update={"coupon_code": coupon}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _claims(session: Session) -> dict[str, int]:
    """Count the firm's redemption rows by status."""
    session.expire_all()
    counted: dict[str, int] = {}
    for status in session.scalars(
        select(PromotionRedemption.status).where(
            PromotionRedemption.is_deleted.is_(False)
        )
    ):
        counted[status] = counted.get(status, 0) + 1
    return counted


def _resave(
    service: SalesInvoiceService, invoice: SalesInvoice, **header: object
) -> SalesInvoice:
    """Send a draft's own line back unchanged, with any header fields."""
    edit = SalesInvoiceCreate(
        **_sent_back(service, invoice, "4").model_dump(exclude_unset=True),
        **header,  # type: ignore[arg-type]
    )
    return service.update_invoice(
        invoice.id, edit, firm_id=invoice.firm_id, actor_id=uuid4()
    )


def test_two_drafts_save_and_the_first_approved_takes_the_last_of_the_offer() -> None:
    """Limit 1: both drafts save, one approval claims, the other is refused."""
    session, setup, service = _counter()
    first, second = _draft(setup, service), _draft(setup, service)

    assert first.grand_total == second.grand_total == Decimal("360.0000")
    assert _claims(session) == {"PENDING": 2}, "a draft holds no claim"

    service.approve_invoice(first.id, firm_scope=setup.firm.id, actor_id=uuid4())
    assert _claims(session) == {"CLAIMED": 1, "PENDING": 1}

    with pytest.raises(ValidationError) as refused:
        service.approve_invoice(second.id, firm_scope=setup.firm.id, actor_id=uuid4())
    session.rollback()
    assert str(refused.value) == (
        "Promotion TENOFF has been claimed as often as it allows. "
        "Re-save the document to price it without."
    )
    stored = session.get(SalesInvoice, second.id)
    assert stored is not None and stored.status == "DRAFT"

    # Saved again without the coupon, it is priced without and approves.
    again = _resave(service, second, coupon_code=None)
    assert again.grand_total == Decimal("400.0000")
    service.approve_invoice(second.id, firm_scope=setup.firm.id, actor_id=uuid4())

    assert _claims(session).get("CLAIMED") == 1
    [coupon] = PromotionReportService(session).coupon_report(firm_scope=setup.firm.id)
    assert (coupon.code, coupon.claimed_count) == ("SAVE10", 1)
    [offer] = PromotionReportService(session).performance_report(
        firm_scope=setup.firm.id
    )
    assert offer.claimed_count == 1


def test_a_save_that_changes_nothing_prices_out_an_offer_that_ran_out() -> None:
    """The refusal says "re-save", so the same bill saved again must reprice."""
    session, setup, service = _counter()
    first, second = _draft(setup, service), _draft(setup, service)
    service.approve_invoice(first.id, firm_scope=setup.firm.id, actor_id=uuid4())

    again = _resave(service, second)

    assert again.grand_total == Decimal("400.0000")
    service.approve_invoice(second.id, firm_scope=setup.firm.id, actor_id=uuid4())
    assert _claims(session).get("CLAIMED") == 1


def test_a_held_an_edited_and_a_cancelled_draft_hold_no_claim() -> None:
    """Nothing short of approval counts against the offer's limit."""
    session, setup, service = _counter()
    draft = _draft(setup, service)
    firm, actor = setup.firm.id, uuid4()

    service.hold_invoice(draft.id, firm_scope=firm, actor_id=actor, note="back soon")
    assert "CLAIMED" not in _claims(session)

    edit = SalesInvoiceCreate(
        **_sent_back(service, draft, "5").model_dump(exclude_unset=True)
    )
    grown = service.update_invoice(draft.id, edit, firm_id=firm, actor_id=actor)
    assert grown.grand_total == Decimal("450.0000"), "the coupon stays"
    assert "CLAIMED" not in _claims(session)
    assert _claims(session).get("PENDING") == 1, "one live order, one pending row"

    service.recall_invoice(draft.id, firm_scope=firm, actor_id=actor)
    service.cancel_invoice(draft.id, firm_scope=firm, actor_id=actor, reason="left")
    assert "CLAIMED" not in _claims(session)
    assert "PENDING" not in _claims(session)

    # The offer is whole: another bill takes it.
    other = _draft(setup, service)
    service.approve_invoice(other.id, firm_scope=firm, actor_id=actor)
    assert _claims(session).get("CLAIMED") == 1


def test_an_order_a_person_types_still_claims_at_its_own_approval() -> None:
    """Only the order a counter bill raises for itself waits for the bill."""
    session = _request_session()
    setup = _Firm(session)
    _coupon_offer(setup)
    orders = SalesOrderService(session)
    order = orders.stage_order(
        SalesOrderCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            order_date=setup.bare_bill().invoice_date,
            coupon_code="SAVE10",
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=setup.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    session.commit()
    assert _claims(session) == {"PENDING": 1}

    orders.approve_order(order.id, firm_scope=setup.firm.id, actor_id=uuid4())

    assert _claims(session) == {"CLAIMED": 1}
