"""A firm decides, per buying document, whether approval is its own step.

Backlog 120, the buying twin of `test_sales_approval_per_document.py`. The
purchase order, the goods receipt and the supplier's bill each have a switch
in `purchase_workflow_settings`. Off, whoever raised the order or the bill
approves it under the code they raised it with, and the desktop's Save does
both. A goods receipt has no approver -- completing one has always taken the
code that raises it -- so its switch only says whether completing is a step
apart from saving. What must stay true:

- the answer is stamped on the document as it is raised, so switching the
  setting never changes a document already made;
- the stamp is the server's -- no request can carry it;
- only the author is let through, and only without an approver's code;
- every check approval runs still runs, the approval limit among them.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.purchase.api.router import approve_purchase_order
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseWorkflowSettingsWrite
from app.purchase.services import PurchaseService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService
from app.purchase_invoice.api.router import approve_purchase_invoice
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from tests.unit.test_purchase_chain_synthesis import _Firm, firm  # noqa: F401

_WHOLE_CHAIN = {"purchase_order_stage": True, "goods_receipt_stage": True}
_BILL_ONLY = {"purchase_order_stage": False, "goods_receipt_stage": False}


def _scope(setup: _Firm, user_id: UUID, *codes: str) -> ResolvedFirmScope:
    """Act in the firm as one user holding exactly these codes."""
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=setup.firm.id,
    )


def _save(setup: _Firm, **values: object) -> None:
    """Save the firm's settings through the service a request reaches."""
    PurchaseWorkflowService(setup.session).update_settings(
        PurchaseWorkflowSettingsWrite.model_validate(values),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )


def _order(setup: _Firm, actor: UUID, price: str = "100") -> PurchaseOrder:
    """Raise and submit a purchase order for ten as one user."""
    service = PurchaseService(setup.session)
    order = service.create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": setup.branch.id,
                "warehouse_id": setup.warehouse.id,
                "vendor_id": setup.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": [
                    {
                        "product_id": setup.product.id,
                        "ordered_quantity": "10",
                        "unit_price": price,
                    }
                ],
            }
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )
    return service.submit_order(order.id, firm_scope=setup.firm.id, actor_id=actor)


def _receipt(setup: _Firm, order: PurchaseOrder, actor: UUID) -> GoodsReceipt:
    """Raise a draft goods receipt of the whole order as one user."""
    line = setup.session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert line is not None
    return GoodsReceiptService(setup.session).create_receipt(
        GoodsReceiptCreate.model_validate(
            {
                "purchase_order_id": order.id,
                "receipt_date": "2026-08-05",
                "lines": [
                    {
                        "purchase_order_line_id": line.id,
                        "line_number": 1,
                        "current_receipt_quantity": "10",
                        "warehouse_id": setup.warehouse.id,
                    }
                ],
            }
        ),
        firm_id=setup.firm.id,
        actor_id=actor,
    )


def _bill(setup: _Firm, actor: UUID, number: str = "S-1") -> PurchaseInvoice:
    """Raise a supplier bill of products as one user."""
    return setup.bills().create_invoice(
        setup.product_bill(number=number), firm_id=setup.firm.id, actor_id=actor
    )


def test_a_firm_that_never_chose_keeps_approval_on_every_document(
    firm: _Firm,  # noqa: F811
) -> None:
    answer = PurchaseWorkflowService(firm.session).settings_response(firm.firm.id)

    assert answer.purchase_order_approval is True
    assert answer.goods_receipt_approval is True
    assert answer.purchase_invoice_approval is True


def test_the_switches_are_saved_and_an_omitted_one_is_left_alone(
    firm: _Firm,  # noqa: F811
) -> None:
    service = PurchaseWorkflowService(firm.session)

    _save(firm, **_WHOLE_CHAIN, purchase_invoice_approval=False)
    first = service.settings_response(firm.firm.id)
    assert first.purchase_invoice_approval is False
    assert first.purchase_order_approval is True
    assert first.goods_receipt_approval is True

    # An editor that never showed the switches sends none of them.
    _save(firm, **_WHOLE_CHAIN)
    assert service.settings_response(firm.firm.id).purchase_invoice_approval is False

    _save(
        firm,
        **_WHOLE_CHAIN,
        purchase_invoice_approval=True,
        purchase_order_approval=False,
    )
    third = service.settings_response(firm.firm.id)
    assert third.purchase_invoice_approval is True
    assert third.purchase_order_approval is False

    trail = firm.session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "purchase_workflow_settings")
    ).all()
    assert trail[-1].after_data is not None
    assert trail[-1].after_data["purchase_order_approval"] is False


def test_no_request_can_carry_the_stamp() -> None:
    assert "approval_step" not in PurchaseOrderCreate.model_fields
    assert "approval_step" not in GoodsReceiptCreate.model_fields
    assert "approval_step" not in PurchaseInvoiceCreate.model_fields


def test_whoever_raised_an_order_approves_it_where_approval_is_no_step(
    firm: _Firm,  # noqa: F811
) -> None:
    _save(firm, **_WHOLE_CHAIN, purchase_order_approval=False)
    buyer = uuid4()
    order = _order(firm, buyer)
    assert order.approval_step is False

    with pytest.raises(AuthorizationError, match="Only whoever raised"):
        approve_purchase_order(
            order.id, _scope(firm, uuid4(), "PURCHASE_CREATE"), firm.session
        )

    answer = approve_purchase_order(
        order.id, _scope(firm, buyer, "PURCHASE_CREATE"), firm.session
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"
    assert answer.data.approval_step is False
    assert answer.data.created_by == buyer


def test_a_firm_with_approval_on_stops_the_buyer_at_it(
    firm: _Firm,  # noqa: F811
) -> None:
    buyer = uuid4()
    order = _order(firm, buyer)
    assert order.approval_step is True

    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_purchase_order(
            order.id, _scope(firm, buyer, "PURCHASE_CREATE"), firm.session
        )
    firm.session.refresh(order)
    assert order.status == "SUBMITTED"

    answer = approve_purchase_order(
        order.id, _scope(firm, uuid4(), "PURCHASE_APPROVE"), firm.session
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_an_order_keeps_the_steps_it_was_made_under(
    firm: _Firm,  # noqa: F811
) -> None:
    buyer = uuid4()
    made_under_approval = _order(firm, buyer)
    _save(firm, **_WHOLE_CHAIN, purchase_order_approval=False)
    made_without = _order(firm, buyer)
    _save(firm, **_WHOLE_CHAIN, purchase_order_approval=True)

    scope = _scope(firm, buyer, "PURCHASE_CREATE")
    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_purchase_order(made_under_approval.id, scope, firm.session)
    answer = approve_purchase_order(made_without.id, scope, firm.session)
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_the_approval_limit_still_judges_an_order_its_author_approves(
    firm: _Firm,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval off removes the second person, never the checks."""
    from app.purchase.services import approval_limit

    _save(firm, **_WHOLE_CHAIN, purchase_order_approval=False)
    buyer = uuid4()
    order = _order(firm, buyer)
    monkeypatch.setattr(
        approval_limit.PurchaseApprovalLimitService,
        "limit_for",
        lambda self, firm_id, user_id: Decimal("500"),
    )

    with pytest.raises(ValidationError, match=r"(?i)limit"):
        approve_purchase_order(
            order.id, _scope(firm, buyer, "PURCHASE_CREATE"), firm.session
        )
    firm.session.rollback()
    firm.session.refresh(order)
    assert order.status == "SUBMITTED"


def test_one_save_books_a_bill_where_no_step_is_switched_on(
    firm: _Firm,  # noqa: F811
) -> None:
    """A firm of one types the supplier's bill and completes it itself."""
    _save(firm, **_BILL_ONLY, purchase_invoice_approval=False)
    clerk = uuid4()
    bill = _bill(firm, clerk)
    assert bill.approval_step is False
    assert bill.status == "DRAFT"

    answer = approve_purchase_invoice(
        bill.id, _scope(firm, clerk, "PURCHASE_CREATE"), None, firm.session
    )

    assert answer.data is not None
    assert answer.data.status == "APPROVED"
    assert answer.data.approval_step is False
    assert answer.data.created_by == clerk
    # The goods came in with it: the chain behind the bill is as real as ever.
    assert firm.stock() == Decimal("10")


def test_a_bill_follows_its_own_switch_and_only_its_author_completes_it(
    firm: _Firm,  # noqa: F811
) -> None:
    _save(firm, **_BILL_ONLY)
    clerk = uuid4()
    waiting = _bill(firm, clerk)
    assert waiting.approval_step is True
    with pytest.raises(AuthorizationError, match="waits for approval"):
        approve_purchase_invoice(
            waiting.id, _scope(firm, clerk, "PURCHASE_CREATE"), None, firm.session
        )

    _save(firm, **_BILL_ONLY, purchase_invoice_approval=False)
    firm.session.refresh(waiting)
    assert waiting.approval_step is True, "a bill already made keeps its step"
    own = _bill(firm, clerk, number="S-2")
    with pytest.raises(AuthorizationError, match="Only whoever raised"):
        approve_purchase_invoice(
            own.id, _scope(firm, uuid4(), "PURCHASE_CREATE"), None, firm.session
        )
    # An approver is still an approver, whoever raised it.
    answer = approve_purchase_invoice(
        own.id, _scope(firm, uuid4(), "PURCHASE_APPROVE"), None, firm.session
    )
    assert answer.data is not None
    assert answer.data.status == "APPROVED"


def test_a_receipt_is_stamped_from_its_own_switch(
    firm: _Firm,  # noqa: F811
) -> None:
    storeman = uuid4()
    order = firm.approved_order()
    first = _receipt(firm, order, storeman)
    assert first.approval_step is True
    service = GoodsReceiptService(firm.session)
    service.cancel_receipt(
        first.id, firm_scope=firm.firm.id, actor_id=storeman, reason="typed twice"
    )

    _save(firm, **_WHOLE_CHAIN, goods_receipt_approval=False)
    second = _receipt(firm, order, storeman)
    assert second.approval_step is False
    answer = service.receipt_response(second)
    assert answer.approval_step is False
    assert answer.created_by == storeman
