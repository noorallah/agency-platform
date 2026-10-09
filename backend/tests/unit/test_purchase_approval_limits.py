"""The largest purchase order a role may approve (BACKLOG 68 row 4).

A buyer limited below an order's grand total cannot approve it: the order stays
submitted and the refusal names the amount it needs. A manager allowed more
approves it, with both figures on the APPROVED event. A person's limit is the
largest among their roles; nobody is limited until the firm sets one; bulk
approval judges each row the same way.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ValidationError
from app.document_framework.models import DocumentLifecycleEvent
from app.document_framework.schemas.bulk_actions import BulkApproveRequest, BulkRow
from app.identity.models import PlatformAdmin, Role, User, UserRole
from app.purchase.api.router import (
    bulk_approve_purchase_orders,
    get_purchase_approval_limits,
    replace_purchase_approval_limits,
)
from app.purchase.models import PurchaseOrder
from app.purchase.schemas import (
    PurchaseOrderStatus,
    RolePurchaseApprovalLimitsWrite,
)
from app.purchase.services import PurchaseService
from app.purchase.services.approval_limit import PurchaseApprovalLimitService
from tests.unit import test_purchase_management as purchases

pytestmark = pytest.mark.typed_document_numbers


class _Desk:
    """One submitted order, a buyer below its total and a manager above it."""

    def __init__(self) -> None:
        """Build the firm, the order and the two people."""
        self.session: Session = purchases._session_factory()()
        self.service, order, self.firm_id, self.actor_id = purchases._submittable_order(
            self.session
        )
        self.order: PurchaseOrder = self.service.submit_order(
            order.id, firm_scope=self.firm_id, actor_id=self.actor_id
        )
        self.total = Decimal(self.order.grand_total).quantize(Decimal("0.01"))
        assert self.total > Decimal("1")
        self.limits = PurchaseApprovalLimitService(self.session)
        self.buyer = self.person("PURCHASE_EXECUTIVE")
        self.manager = self.person("PURCHASE_MANAGER")
        self.limits.replace_limits(
            [
                ("PURCHASE_EXECUTIVE", self.total - Decimal("1")),
                ("PURCHASE_MANAGER", self.total * 10),
            ],
            firm_id=self.firm_id,
            actor_id=self.actor_id,
        )

    def person(self, *role_codes: str, in_this_firm: bool = True) -> UUID:
        """Create a user holding the given roles in this firm."""
        user = User(
            email=f"{uuid4().hex[:8]}@buy.test",
            full_name="Buying person",
            password_hash="x",
        )
        self.session.add(user)
        self.session.flush()
        for code in role_codes:
            role = self.session.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, name=code.title())
                self.session.add(role)
                self.session.flush()
            self.session.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    firm_id=self.firm_id if in_this_firm else uuid4(),
                )
            )
        self.session.commit()
        return user.id

    def approve_as(self, user_id: UUID) -> str:
        """Approve the order as somebody; return its status."""
        return self.service.approve_order(
            self.order.id, firm_scope=self.firm_id, actor_id=user_id
        ).status

    def status(self) -> str:
        """Return the order's status as stored."""
        self.session.expire_all()
        return self.service.get_order(self.order.id, firm_scope=self.firm_id).status

    def scope(self, user_id: UUID, *codes: str) -> ResolvedFirmScope:
        """Build the scope a handler receives once authorized."""
        return ResolvedFirmScope(
            principal=purchases._principal(user_id, set(codes)),
            firm_id=self.firm_id,
        )


@pytest.fixture
def desk() -> _Desk:
    """Build the firm."""
    return _Desk()


def test_above_the_limit_stays_submitted_and_names_what_it_needs(
    desk: _Desk,
) -> None:
    """The buyer's limit is one rupee short of the order."""
    with pytest.raises(
        ValidationError,
        match=rf"total of {desk.total} is above your approval limit of "
        rf"{desk.total - 1}.*at least {desk.total}",
    ):
        desk.approve_as(desk.buyer)
    desk.session.rollback()
    assert desk.status() == PurchaseOrderStatus.SUBMITTED.value


def test_a_higher_limit_approves_and_the_event_records_both_figures(
    desk: _Desk,
) -> None:
    """The manager clears it; the APPROVED event names who and both amounts."""
    assert desk.approve_as(desk.manager) == PurchaseOrderStatus.APPROVED.value
    event = desk.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == desk.order.id,
            DocumentLifecycleEvent.action == "APPROVED",
        )
    )
    assert event is not None
    assert event.actor_id == desk.manager
    assert event.details_json is not None
    assert event.details_json["approval_limit"] == {
        "order_amount": str(desk.total),
        "approver_limit": str((desk.total * 10).quantize(Decimal("0.01"))),
    }


def test_exactly_at_the_limit_is_within_it(desk: _Desk) -> None:
    """A limit equal to the total is not exceeded."""
    exact = desk.person("STOREKEEPER")
    desk.limits.replace_limits(
        [("STOREKEEPER", desk.total)], firm_id=desk.firm_id, actor_id=desk.actor_id
    )
    assert desk.approve_as(exact) == PurchaseOrderStatus.APPROVED.value


def test_the_largest_limit_among_a_person_s_roles_counts(desk: _Desk) -> None:
    """A buyer who is also a manager approves up to the manager's limit."""
    both = desk.person("PURCHASE_EXECUTIVE", "PURCHASE_MANAGER")
    assert desk.limits.limit_for(desk.firm_id, both) == (desk.total * 10).quantize(
        Decimal("0.01")
    )
    assert desk.approve_as(both) == PurchaseOrderStatus.APPROVED.value


def test_nobody_is_limited_until_the_firm_says_so(desk: _Desk) -> None:
    """A role with no row, another firm's role, an administrator: no limit."""
    assert desk.limits.limit_for(desk.firm_id, desk.person("ACCOUNTANT")) is None
    elsewhere = desk.person("PURCHASE_EXECUTIVE", in_this_firm=False)
    assert desk.limits.limit_for(desk.firm_id, elsewhere) is None
    admin = desk.person("PURCHASE_EXECUTIVE")
    desk.session.add(PlatformAdmin(user_id=admin, scope="ALL_FIRMS"))
    desk.session.commit()
    assert desk.limits.limit_for(desk.firm_id, admin) is None
    desk.limits.replace_limits([], firm_id=desk.firm_id, actor_id=desk.actor_id)
    assert desk.approve_as(desk.buyer) == PurchaseOrderStatus.APPROVED.value


def test_bulk_approval_judges_each_row_by_the_same_limit(desk: _Desk) -> None:
    """The buyer's bulk run refuses the order by name; the manager's approves."""
    request = BulkApproveRequest(
        items=[BulkRow(id=desk.order.id, version=desk.order.version)]
    )
    refused = bulk_approve_purchase_orders(
        data=request, scope=desk.scope(desk.buyer, "PURCHASE_APPROVE"), db=desk.session
    ).data
    assert refused is not None
    assert (refused.done, refused.refused) == (0, 1)
    assert "approval limit" in (refused.results[0].message or "")
    assert desk.status() == PurchaseOrderStatus.SUBMITTED.value
    approved = bulk_approve_purchase_orders(
        data=request,
        scope=desk.scope(desk.manager, "PURCHASE_APPROVE"),
        db=desk.session,
    ).data
    assert approved is not None
    assert (approved.done, approved.refused) == (1, 0)
    assert desk.status() == PurchaseOrderStatus.APPROVED.value


def test_the_settings_endpoints_replace_and_list_the_limits(desk: _Desk) -> None:
    """A role left out of the write has no limit afterwards."""
    written = replace_purchase_approval_limits(
        data=RolePurchaseApprovalLimitsWrite.model_validate(
            {"limits": [{"role_code": "PURCHASE_MANAGER", "max_order_amount": "500"}]}
        ),
        scope=desk.scope(desk.actor_id, "PURCHASE_MANAGE_SETTINGS"),
        db=desk.session,
    ).data
    assert written is not None
    assert [(i.role_code, i.max_order_amount) for i in written.limits] == [
        ("PURCHASE_MANAGER", Decimal("500.00"))
    ]
    listed = get_purchase_approval_limits(
        scope=desk.scope(desk.actor_id, "PURCHASE_VIEW"), db=desk.session
    ).data
    assert listed is not None
    assert len(listed.limits) == 1
    assert desk.limits.limit_for(desk.firm_id, desk.buyer) is None
    with pytest.raises(ValidationError, match="listed twice"):
        desk.limits.replace_limits(
            [("PURCHASE_MANAGER", Decimal("1")), ("purchase_manager", Decimal("2"))],
            firm_id=desk.firm_id,
            actor_id=desk.actor_id,
        )


def test_a_negative_limit_is_refused_by_the_schema() -> None:
    """Below zero never reaches the service."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        RolePurchaseApprovalLimitsWrite.model_validate(
            {"limits": [{"role_code": "X", "max_order_amount": "-1"}]}
        )


def test_an_order_a_bill_raised_is_not_judged(desk: _Desk) -> None:
    """The chain approves its own order with the limit off."""
    PurchaseService(desk.session).stage_approval(
        desk.order.id,
        firm_scope=desk.firm_id,
        actor_id=desk.buyer,
        enforce_limit=False,
    )
    desk.session.commit()
    assert desk.status() == PurchaseOrderStatus.APPROVED.value


def test_a_limit_on_a_role_nobody_holds_is_refused(desk: _Desk) -> None:
    """D-CFG-27: a mistyped role was kept, bound nobody and said nothing."""
    with pytest.raises(ValidationError, match="not a role of this firm"):
        desk.limits.replace_limits(
            [("PURCHASE_MANGER", Decimal("5"))],
            firm_id=desk.firm_id,
            actor_id=desk.actor_id,
        )
    desk.session.rollback()
    assert [row.role_code for row in desk.limits.limits(desk.firm_id)] == [
        "PURCHASE_EXECUTIVE",
        "PURCHASE_MANAGER",
    ]
    rows = desk.limits.replace_limits(
        [("purchase_manager", Decimal("5"))],
        firm_id=desk.firm_id,
        actor_id=desk.actor_id,
    )
    assert [row.role_code for row in rows] == ["PURCHASE_MANAGER"]
    assert desk.limits.limit_for(desk.firm_id, desk.manager) == Decimal("5.00")
