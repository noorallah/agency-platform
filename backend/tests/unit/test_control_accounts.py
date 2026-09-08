"""The control-account mapping has a screen, and a guard on re-pointing.

`firm_control_accounts` tells posting which account is Inventory, Trade
Receivables or Output Tax. Until 2026-09-08 it had no endpoint and no screen:
opening the books mapped all 24, and changing one afterwards was SQL. These
pin the overview every purpose appears in, the ordinary edit, and the one
refusal -- a purpose with postings behind it stays where it is, because
re-pointing it leaves two accounts each holding part of one story.
"""

# ruff: noqa: D101,D102,D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import optional_firm_scope, required_firm_scope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.api.router import assign_control_account, list_control_accounts
from app.finance.models import LedgerAccount
from app.finance.schemas import (
    AccountTypeEnum,
    ControlAccountAssign,
    LedgerAccountCreate,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.finance_service import FinanceService
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import UserFirm

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    firm = Firm(
        name="Acme",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=_ACTOR
    )
    session.commit()
    return firm


def _account(session: Session, firm: Firm, code: str, name: str) -> LedgerAccount:
    """Create a second asset account in the seeded Current Assets group."""
    group_id = session.scalar(
        select(LedgerAccount.account_group_id).where(
            LedgerAccount.firm_id == firm.id, LedgerAccount.code == "1200"
        )
    )
    assert group_id is not None
    return FinanceService(session).create_ledger_account(
        LedgerAccountCreate(
            account_group_id=group_id,
            code=code,
            name=name,
            account_type=AccountTypeEnum.ASSET,
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )


def _post_a_sale(session: Session, firm: Firm) -> None:
    DocumentPostingService(session).post_sales_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="SI-1",
        invoice_date=date(2026, 6, 1),
        taxable_amount=Decimal("1000"),
        tax_amount=Decimal("180"),
        total_amount=Decimal("1180"),
        actor_id=_ACTOR,
    )
    session.commit()


class TestOverview:
    def test_lists_every_purpose_in_order_with_its_account(self) -> None:
        session = _session()
        firm = _firm(session)

        views = ControlAccountService(session).overview(firm.id)

        assert [v.purpose for v in views] == list(ControlAccountPurpose)
        assert all(v.ledger_account_id is not None for v in views)
        inventory = next(
            v for v in views if v.purpose is ControlAccountPurpose.INVENTORY
        )
        assert inventory.label == "Inventory"
        assert inventory.account_code == "1200"
        assert inventory.expected_types == ("ASSET",)
        assert inventory.posted_lines == 0

    def test_shows_the_gap_when_a_purpose_is_unmapped(self) -> None:
        session = _session()
        firm = Firm(
            name="Bare",
            code="BARE",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(firm)
        session.commit()

        views = ControlAccountService(session).overview(firm.id)

        assert len(views) == len(ControlAccountPurpose)
        assert all(v.ledger_account_id is None for v in views)
        assert all(v.account_code is None for v in views)

    def test_counts_posted_lines_on_the_mapped_account(self) -> None:
        session = _session()
        firm = _firm(session)
        _post_a_sale(session, firm)

        views = {v.purpose: v for v in ControlAccountService(session).overview(firm.id)}

        assert views[ControlAccountPurpose.ACCOUNTS_RECEIVABLE].posted_lines == 1
        assert views[ControlAccountPurpose.SALES_REVENUE].posted_lines == 1
        assert views[ControlAccountPurpose.OUTPUT_TAX].posted_lines == 1
        assert views[ControlAccountPurpose.INVENTORY].posted_lines == 0


class TestReassign:
    def test_re_points_a_purpose_nothing_has_posted_to(self) -> None:
        session = _session()
        firm = _firm(session)
        stock = _account(session, firm, "1250", "Stock in hand")
        service = ControlAccountService(session)

        service.reassign(
            firm.id, ControlAccountPurpose.INVENTORY, stock.id, actor_id=_ACTOR
        )
        session.commit()

        assert service.resolve(firm.id, ControlAccountPurpose.INVENTORY) == stock.id
        row = session.scalar(
            select(AuditLog).where(AuditLog.action == "control_account.assigned")
        )
        assert row is not None
        assert row.after_data is not None
        assert row.after_data["purpose"] == "INVENTORY"
        assert row.before_data is not None
        assert row.before_data["ledger_account_id"] is not None

    def test_refuses_once_lines_have_posted_to_the_current_account(self) -> None:
        session = _session()
        firm = _firm(session)
        _post_a_sale(session, firm)
        other = _account(session, firm, "1150", "Debtors (new)")
        service = ControlAccountService(session)
        before = service.resolve(firm.id, ControlAccountPurpose.ACCOUNTS_RECEIVABLE)

        with pytest.raises(BusinessRuleError, match="1 posted line on 1100"):
            service.reassign(
                firm.id,
                ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
                other.id,
                actor_id=_ACTOR,
            )

        assert service.resolve(firm.id, ControlAccountPurpose.ACCOUNTS_RECEIVABLE) == (
            before
        )

    def test_choosing_the_same_account_again_is_not_a_change(self) -> None:
        session = _session()
        firm = _firm(session)
        _post_a_sale(session, firm)
        service = ControlAccountService(session)
        current = service.resolve(firm.id, ControlAccountPurpose.ACCOUNTS_RECEIVABLE)

        service.reassign(
            firm.id, ControlAccountPurpose.ACCOUNTS_RECEIVABLE, current, actor_id=_ACTOR
        )

        assert service.resolve(firm.id, ControlAccountPurpose.ACCOUNTS_RECEIVABLE) == (
            current
        )

    def test_still_refuses_the_wrong_classification(self) -> None:
        session = _session()
        firm = _firm(session)
        revenue = session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.firm_id == firm.id, LedgerAccount.code == "4000"
            )
        )
        assert revenue is not None

        with pytest.raises(ValidationError, match="INVENTORY must post to a ASSET"):
            ControlAccountService(session).reassign(
                firm.id, ControlAccountPurpose.INVENTORY, revenue.id, actor_id=_ACTOR
            )


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset({"ACCOUNTANT"}),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def test_the_routes_read_with_account_view_and_write_with_account_manage() -> None:
    session = _session()
    firm = _firm(session)
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    stock = _account(session, firm, "1250", "Stock in hand")

    viewer = required_firm_scope(
        optional_firm_scope(
            principal=_principal(user_id, {"ACCOUNT_VIEW"}),
            db=session,
            x_firm_id=firm.id,
        )
    )
    listed = list_control_accounts(viewer, session).data
    assert len(listed) == len(ControlAccountPurpose)
    assert listed[0].purpose == "ACCOUNTS_RECEIVABLE"

    manager = required_firm_scope(
        optional_firm_scope(
            principal=_principal(user_id, {"ACCOUNT_VIEW", "ACCOUNT_MANAGE"}),
            db=session,
            x_firm_id=firm.id,
        )
    )
    response = assign_control_account(
        ControlAccountPurpose.INVENTORY,
        ControlAccountAssign(ledger_account_id=stock.id),
        manager,
        session,
    )
    assert response.data.account_code == "1250"
    assert response.message == "Inventory posts to 1250 Stock in hand."
