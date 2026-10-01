"""Bulk approval and cancellation of orders (backlog 56 A).

`docs/BULK_APPROVAL_MIGRATION_AND_YEAR_DATA.md` section 2: each ticked row is
acted on by the service a single action uses and committed on its own, so a
refused row is reported with its reason and never holds back the rest.
"""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope
from app.document_framework.schemas.bulk_actions import (
    MAX_BULK_ROWS,
    BulkApproveRequest,
    BulkCancelRequest,
    BulkRow,
)
from app.purchase.api.router import bulk_approve_purchase_orders
from app.purchase.schemas import PurchaseOrderStatus
from app.sales_order.api.router import (
    bulk_approve_sales_orders,
    bulk_cancel_sales_orders,
)
from app.sales_order.models import SalesOrder
from app.sales_order.services import SalesOrderService
from tests.unit import test_purchase_management as purchases
from tests.unit import test_sales_order_module as sales


def _sales_orders(count: int) -> tuple[Session, UUID, list[SalesOrder]]:
    """Seed ``count`` draft sales orders for one customer of one firm."""
    session = sales._session_factory()()
    firm = sales._firm(session)
    branch = sales._branch(session, firm_id=firm.id)
    warehouse = sales._warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = sales._customer(session, firm_id=firm.id)
    product = sales._product(session, firm_id=firm.id)
    service = SalesOrderService(session)
    orders = [
        service.create_order(
            sales._order_for(
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        for _ in range(count)
    ]
    return session, firm.id, orders


def _scope(firm_id: UUID, *codes: str) -> ResolvedFirmScope:
    """Build the scope a bulk handler receives once authorized."""
    return ResolvedFirmScope(
        principal=sales._principal(uuid4(), set(codes)), firm_id=firm_id
    )


def test_each_order_is_approved_on_its_own_and_a_refusal_holds_nothing_back() -> None:
    """One good, one already approved, one changed since read, one named twice."""
    session, firm_id, (good, done_before, changed) = _sales_orders(3)
    service = SalesOrderService(session)
    service.approve_order(done_before.id, firm_scope=firm_id, actor_id=uuid4())

    result = bulk_approve_sales_orders(
        data=BulkApproveRequest(
            items=[
                BulkRow(id=good.id, version=good.version),
                BulkRow(id=done_before.id),
                BulkRow(id=changed.id, version=changed.version - 1),
                BulkRow(id=good.id, version=good.version),
            ]
        ),
        scope=_scope(firm_id, "SALES_APPROVE"),
        db=session,
    ).data

    assert result is not None
    assert (result.done, result.refused) == (1, 2)
    outcomes = {row.id: row for row in result.results}
    assert len(result.results) == 3, "a row named twice is acted on once"
    assert outcomes[good.id].outcome == "DONE"
    assert outcomes[good.id].number == good.order_number
    assert outcomes[done_before.id].outcome == "REFUSED"
    assert outcomes[done_before.id].message
    assert outcomes[changed.id].outcome == "REFUSED"
    assert "changed after the list was read" in (outcomes[changed.id].message or "")
    session.expire_all()
    assert service.get_order(good.id, firm_scope=firm_id).status == "APPROVED"
    assert service.get_order(changed.id, firm_scope=firm_id).status == "DRAFT"


def test_another_firm_s_order_is_refused_as_not_found() -> None:
    """Every row is read through the firm's own scope, never by id alone."""
    session, firm_id, (order,) = _sales_orders(1)

    result = bulk_approve_sales_orders(
        data=BulkApproveRequest(items=[BulkRow(id=order.id)]),
        scope=_scope(uuid4(), "SALES_APPROVE"),
        db=session,
    ).data

    assert result is not None
    assert (result.done, result.refused) == (0, 1)
    assert result.results[0].number is None
    session.expire_all()
    assert (
        SalesOrderService(session).get_order(order.id, firm_scope=firm_id).status
        == "DRAFT"
    )


def test_a_bulk_cancel_records_the_one_reason_on_every_order() -> None:
    """Cancel needs a reason, and each order keeps it."""
    session, firm_id, orders = _sales_orders(2)

    result = bulk_cancel_sales_orders(
        data=BulkCancelRequest(
            items=[BulkRow(id=order.id) for order in orders],
            reason="  Customer called off the season's order  ",
        ),
        scope=_scope(firm_id, "SALES_CANCEL"),
        db=session,
    ).data

    assert result is not None
    assert (result.done, result.refused) == (2, 0)
    session.expire_all()
    for order in orders:
        row = SalesOrderService(session).get_order(order.id, firm_scope=firm_id)
        assert row.status == "CANCELLED"


def test_a_bulk_request_needs_a_reason_to_cancel_and_at_most_a_hundred_rows() -> None:
    """A blank reason records nothing; more rows than one request may name."""
    with pytest.raises(SchemaError):
        BulkCancelRequest(items=[BulkRow(id=uuid4())], reason="   ")
    with pytest.raises(SchemaError):
        BulkApproveRequest(items=[])
    with pytest.raises(SchemaError):
        BulkApproveRequest(
            items=[BulkRow(id=uuid4()) for _ in range(MAX_BULK_ROWS + 1)]
        )


# The purchase fixtures type their order numbers, as their own module does.
@pytest.mark.typed_document_numbers
def test_purchase_orders_are_approved_in_bulk_once_submitted() -> None:
    """The same runner under PURCHASE_APPROVE; a stale row and a stranger refused."""
    session = purchases._session_factory()()
    service, order, firm_id, actor_id = purchases._submittable_order(session)
    submitted = service.submit_order(order.id, firm_scope=firm_id, actor_id=actor_id)
    scope = _scope(firm_id, "PURCHASE_APPROVE")

    refused = bulk_approve_purchase_orders(
        data=BulkApproveRequest(
            items=[
                BulkRow(id=order.id, version=submitted.version - 1),
                BulkRow(id=uuid4()),
            ]
        ),
        scope=scope,
        db=session,
    ).data
    assert refused is not None
    assert (refused.done, refused.refused) == (0, 2)

    approved = bulk_approve_purchase_orders(
        data=BulkApproveRequest(
            items=[BulkRow(id=order.id, version=submitted.version)]
        ),
        scope=scope,
        db=session,
    ).data
    assert approved is not None
    assert (approved.done, approved.refused) == (1, 0)
    assert approved.results[0].number == order.po_number
    session.expire_all()
    assert (
        service.get_order(order.id, firm_scope=firm_id).status
        == PurchaseOrderStatus.APPROVED.value
    )
