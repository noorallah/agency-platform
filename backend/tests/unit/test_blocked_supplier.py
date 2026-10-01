"""A blocked supplier (backlog 69 row 4).

Blocking stops new business -- no new order, no new or edited bill -- and says
why to whoever meets it. What is already billed can still be approved, paid
and returned: a block does not cancel what is owed.
"""

import pytest
from sqlalchemy import create_engine
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
