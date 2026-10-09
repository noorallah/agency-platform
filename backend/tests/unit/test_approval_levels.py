"""Approval in levels by amount, and rejection (PLT-1, decision A131).

A supplier bill of about a thousand needs the buyer at level 1 and finance at
level 2 from 500 up. The buyer cannot approve it outright; they sign level 1.
They cannot sign level 2 as well. Finance approves it, which signs the last
level and approves the bill in one step. A rejection needs a reason, clears
the sign-offs and takes the bill off the buyer's queue until it is changed.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.approvals.services import (
    ApprovalChainService,
    ApprovalDecisionWrite,
    ApprovalRejectWrite,
    ApprovalRulesWrite,
)
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.identity.models import Role, User, UserRole
from app.purchase_invoice.models import PurchaseInvoice
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm with a draft supplier bill and the two-level rule."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="APPR")
    built.stages(order=False, receipt=False)
    bill = built.bills().create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    built.bill_id = bill.id  # type: ignore[attr-defined]
    # A rule names a role the firm has (D-CFG-27), so the roles come first.
    built.session.add_all(
        Role(code=code, name=code.title()) for code in ("BUYER", "FINANCE", "CFO")
    )
    built.session.flush()
    ApprovalChainService(built.session).replace_rules(
        built.firm.id,
        "PURCHASE_INVOICE",
        ApprovalRulesWrite.model_validate(
            {
                "rules": [
                    {"level": 1, "min_amount": "500", "role_code": "BUYER"},
                    {"level": 2, "min_amount": "500", "role_code": "FINANCE"},
                ]
            }
        ),
        actor_id=built.actor_id,
    )
    return built


def _person(firm: _Firm, code: str) -> UUID:
    user = User(email=f"{uuid4().hex[:8]}@appr.test", full_name=code, password_hash="x")
    firm.session.add(user)
    firm.session.flush()
    role = firm.session.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=code.title())
        firm.session.add(role)
        firm.session.flush()
    firm.session.add(UserRole(user_id=user.id, role_id=role.id, firm_id=firm.firm.id))
    firm.session.commit()
    return user.id


def _approve(firm: _Firm, actor: UUID) -> PurchaseInvoice:
    return firm.bills().approve_invoice(
        firm.bill_id,  # type: ignore[attr-defined]
        firm_scope=firm.firm.id,
        actor_id=actor,
    )


def _sign(firm: _Firm, actor: UUID) -> object:
    return ApprovalChainService(firm.session).sign_off(
        ApprovalDecisionWrite(
            document_type="PURCHASE_INVOICE",
            document_id=firm.bill_id,  # type: ignore[attr-defined]
        ),
        firm_id=firm.firm.id,
        actor_id=actor,
        approve=lambda: _approve(firm, actor),
    )


def test_two_levels_are_signed_in_order_by_two_people(firm: _Firm) -> None:
    buyer = _person(firm, "BUYER")
    finance = _person(firm, "FINANCE")
    with pytest.raises(ValidationError, match="level 1 sign-off by BUYER"):
        _approve(firm, buyer)

    service = ApprovalChainService(firm.session)
    assert [
        item.document_id
        for item in service.pending_for(
            firm.firm.id, buyer, approve_codes={"PURCHASE_APPROVE"}
        )
    ] == [
        firm.bill_id
    ]  # type: ignore[attr-defined]

    status = _sign(firm, buyer)
    assert status.next_level == 2  # type: ignore[attr-defined]
    with pytest.raises(ValidationError, match="signed an earlier level"):
        _sign(firm, buyer)
    assert (
        service.pending_for(firm.firm.id, buyer, approve_codes={"PURCHASE_APPROVE"})
        == []
    )

    approved = _approve(firm, finance)
    assert approved.status == "APPROVED"


def test_the_last_sign_off_approves_the_document(firm: _Firm) -> None:
    _sign(firm, _person(firm, "BUYER"))
    status = _sign(firm, _person(firm, "FINANCE"))
    assert status.status == "APPROVED"  # type: ignore[attr-defined]


def test_a_rejection_needs_a_reason_and_clears_the_sign_offs(firm: _Firm) -> None:
    buyer = _person(firm, "BUYER")
    finance = _person(firm, "FINANCE")
    _sign(firm, buyer)
    service = ApprovalChainService(firm.session)
    status = service.reject(
        ApprovalRejectWrite(
            document_type="PURCHASE_INVOICE",
            document_id=firm.bill_id,  # type: ignore[attr-defined]
            reason="Rate is above the agreed price",
        ),
        firm_id=firm.firm.id,
        actor_id=finance,
    )
    assert status.rejected_reason == "Rate is above the agreed price"
    assert status.next_level == 1
    assert (
        service.pending_for(firm.firm.id, buyer, approve_codes={"PURCHASE_APPROVE"})
        == []
    )


def test_a_level_needs_the_one_below_it(firm: _Firm) -> None:
    with pytest.raises(ValidationError, match="needs a level 1"):
        ApprovalChainService(firm.session).replace_rules(
            firm.firm.id,
            "SALES_ORDER",
            ApprovalRulesWrite.model_validate(
                {"rules": [{"level": 2, "min_amount": "0", "role_code": "X"}]}
            ),
            actor_id=firm.actor_id,
        )


def test_a_bill_below_every_rule_approves_as_before(firm: _Firm) -> None:
    ApprovalChainService(firm.session).replace_rules(
        firm.firm.id,
        "PURCHASE_INVOICE",
        ApprovalRulesWrite.model_validate(
            {"rules": [{"level": 1, "min_amount": "1000000", "role_code": "CFO"}]}
        ),
        actor_id=firm.actor_id,
    )
    assert _approve(firm, firm.actor_id).status == "APPROVED"


def test_a_rule_on_a_role_nobody_holds_is_refused(firm: _Firm) -> None:
    """D-CFG-27: a mistyped role was kept, and nobody could sign its level."""
    service = ApprovalChainService(firm.session)

    def write(role_code: str) -> list[str]:
        rows = service.replace_rules(
            firm.firm.id,
            "PURCHASE_INVOICE",
            ApprovalRulesWrite.model_validate(
                {"rules": [{"level": 1, "min_amount": "500", "role_code": role_code}]}
            ),
            actor_id=firm.actor_id,
        )
        return [row.role_code for row in rows]

    with pytest.raises(ValidationError, match="not a role of this firm"):
        write("BUYR")
    firm.session.rollback()
    assert sorted(
        rule.role_code for rule in service.rules(firm.firm.id, "PURCHASE_INVOICE")
    ) == ["BUYER", "FINANCE"]
    assert write("buyer") == ["BUYER"]
