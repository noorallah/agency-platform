"""A blocked supplier (backlog 69 row 4).

Blocking stops new business -- no new order, no new or edited bill -- and says
why to whoever meets it. What is already billed can still be approved, paid
and returned: a block does not cancel what is owed.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.vendors.schemas.vendor import VendorUpdate
from app.vendors.services.vendor_service import VendorService
from tests.unit.test_purchase_chain_synthesis import _Firm


@pytest.fixture
def firm() -> _Firm:
    """Build the purchase-chain firm on a fresh store, bills typed directly."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)())
    built.stages(order=False, receipt=False)
    return built


def _block(firm: _Firm, reason: str | None) -> None:
    """Block the firm's supplier through the service, as the form would."""
    VendorService(firm.session).update(
        firm.vendor.id,
        VendorUpdate.model_validate(
            {
                "code": firm.vendor.code,
                "name": firm.vendor.name,
                "status": "BLOCKED",
                "blocked_reason": reason,
            }
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )


def test_a_block_needs_a_reason_and_unblocking_drops_it(firm: _Firm) -> None:
    """No reason, no block; back to ACTIVE, the reason goes."""
    with pytest.raises(ValidationError, match="Say why the supplier is blocked"):
        _block(firm, "  ")
    firm.session.rollback()
    _block(firm, "Quality complaints, March lot")
    assert firm.vendor.blocked_reason == "Quality complaints, March lot"

    VendorService(firm.session).update(
        firm.vendor.id,
        VendorUpdate.model_validate(
            {"code": firm.vendor.code, "name": firm.vendor.name, "status": "ACTIVE"}
        ),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert firm.vendor.blocked_reason is None


def test_no_new_bill_or_order_and_the_reason_is_said(firm: _Firm) -> None:
    """A new bill raises an order first; both name the block and its reason."""
    _block(firm, "Quality complaints, March lot")
    with pytest.raises(ValidationError, match="blocked: Quality complaints"):
        firm.bills().create_invoice(
            firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
        )


def test_what_was_billed_before_can_still_be_approved(firm: _Firm) -> None:
    """The draft entered before the block is approved; editing it is refused."""
    bills = firm.bills()
    draft = bills.create_invoice(
        firm.product_bill(), firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    _block(firm, "Disputed rates")

    with pytest.raises(ValidationError, match="is blocked: Disputed rates"):
        bills.update_invoice(
            draft.id,
            firm.product_bill(quantity="5"),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    approved = bills.approve_invoice(
        draft.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    assert approved.status == "APPROVED"


def test_an_approved_order_is_marked_sent_and_found_when_not(firm: _Firm) -> None:
    """Backlog 69 row 6: when and how it went; "never sent" is a filter."""
    from app.document_framework.models import DocumentLifecycleEvent
    from app.purchase.schemas import PurchaseOrderListFilters
    from app.purchase.services import PurchaseService

    orders = PurchaseService(firm.session)
    order = firm.approved_order()

    def listed(sent: bool) -> list[object]:
        """Return the ids the list gives for one answer to "sent?"."""
        rows, _ = orders.list_orders(
            firm_scope=firm.firm.id,
            filters=PurchaseOrderListFilters(sent=sent),
            page=1,
            page_size=50,
            search=None,
            sort_by="created_at",
            descending=True,
        )
        return [row.id for row in rows]

    assert listed(False) == [order.id] and listed(True) == []
    sent = orders.mark_sent(
        order.id, via="WHATSAPP", firm_scope=firm.firm.id, actor_id=firm.actor_id
    )
    assert sent.sent_via == "WHATSAPP" and sent.sent_at is not None
    assert listed(True) == [order.id] and listed(False) == []
    event = firm.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == order.id,
            DocumentLifecycleEvent.action == "SENT",
        )
    )
    assert event is not None


def test_a_draft_cannot_be_marked_sent(firm: _Firm) -> None:
    """Only an approved order is a promise worth sending."""
    from app.purchase.schemas import PurchaseOrderCreate
    from app.purchase.services import PurchaseService

    orders = PurchaseService(firm.session)
    draft = orders.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": [
                    {
                        "product_id": firm.product.id,
                        "ordered_quantity": "1",
                        "unit_price": "100",
                    }
                ],
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    with pytest.raises(ValidationError, match="Only an approved order"):
        orders.mark_sent(
            draft.id, via="EMAIL", firm_scope=firm.firm.id, actor_id=firm.actor_id
        )
