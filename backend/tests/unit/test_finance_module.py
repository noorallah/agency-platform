"""Finance master, journal posting, reporting, and API scope tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.api.router import (
    create_journal_entry,
    post_journal_entry,
    trial_balance,
)
from app.finance.models import (
    AccountingPeriod,
    CostCenter,
    FinancialYear,
    GLPosting,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    LedgerBalance,
    PeriodStatus,
)
from app.finance.schemas import (
    AccountGroupCreate,
    AccountingPeriodCreate,
    AccountingPeriodUpdate,
    AccountTypeEnum,
    CostCenterCreate,
    FinancialYearCreate,
    JournalEntryCreate,
    JournalTypeCreate,
    LedgerAccountCreate,
    PeriodStatusEnum,
    VoucherTypeCreate,
)
from app.finance.services import (
    FinanceService,
    GeneralLedgerService,
    JournalEntryEngine,
    JournalLineData,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.opening_setup import CHART, seed_finance_setup
from app.firms.models import Firm
from app.identity.models import UserFirm


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper.

    Routers no longer carry a private resolver; membership is validated once in
    ``app.common.scope`` against the platform store.
    """
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database for service and API tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str = "ACME") -> Firm:
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


class _Book:
    """Hold the master records a journal entry needs."""

    def __init__(self, session: Session, firm_id: UUID, actor_id: UUID) -> None:
        service = FinanceService(session)
        self.year = service.create_financial_year(
            FinancialYearCreate(
                code="FY2027",
                name="2026-2027",
                starts_on=date(2026, 4, 1),
                ends_on=date(2027, 3, 31),
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.period = service.create_accounting_period(
            AccountingPeriodCreate(
                financial_year_id=self.year.id,
                period_number=1,
                code="P1",
                name="April 2026",
                starts_on=date(2026, 4, 1),
                ends_on=date(2026, 4, 30),
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.asset_group = service.create_account_group(
            AccountGroupCreate(
                code="CA", name="Current Assets", account_type=AccountTypeEnum.ASSET
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.income_group = service.create_account_group(
            AccountGroupCreate(
                code="REV", name="Revenue", account_type=AccountTypeEnum.INCOME
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.cash = service.create_ledger_account(
            LedgerAccountCreate(
                account_group_id=self.asset_group.id,
                code="1000",
                name="Cash",
                account_type=AccountTypeEnum.ASSET,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.sales = service.create_ledger_account(
            LedgerAccountCreate(
                account_group_id=self.income_group.id,
                code="4000",
                name="Sales",
                account_type=AccountTypeEnum.INCOME,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.journal_type = service.create_journal_type(
            JournalTypeCreate(code="GEN", name="General"),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        self.voucher_type = service.create_voucher_type(
            VoucherTypeCreate(code="JV", name="Journal Voucher"),
            firm_id=firm_id,
            actor_id=actor_id,
        )


def _sale_lines(book: _Book, amount: str) -> list[JournalLineData]:
    return [
        JournalLineData(ledger_account_id=book.cash.id, debit_amount=Decimal(amount)),
        JournalLineData(ledger_account_id=book.sales.id, credit_amount=Decimal(amount)),
    ]


def test_finance_masters_enforce_codes_hierarchy_and_audit() -> None:
    """Masters reject mismatched types and duplicates, and emit audit events."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    service = FinanceService(session)
    book = _Book(session, firm.id, actor_id)

    # A ledger account must share its group's account type.
    with pytest.raises(ValidationError, match="share its group's account type"):
        service.create_ledger_account(
            LedgerAccountCreate(
                account_group_id=book.asset_group.id,
                code="4999",
                name="Misfiled Revenue",
                account_type=AccountTypeEnum.INCOME,
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    # Codes are unique per firm.
    service.create_cost_center(
        CostCenterCreate(code="CC1", name="First"),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    with pytest.raises(ConflictError):
        service.create_cost_center(
            CostCenterCreate(code="CC1", name="Duplicate"),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    # Financial years may not overlap.
    with pytest.raises(ValidationError, match="overlaps"):
        service.create_financial_year(
            FinancialYearCreate(
                code="FY2027B",
                name="Overlapping",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 12, 31),
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    # A period must sit inside its financial year.
    with pytest.raises(ValidationError, match="inside its financial year"):
        service.create_accounting_period(
            AccountingPeriodCreate(
                financial_year_id=book.year.id,
                period_number=2,
                code="P99",
                name="Outside",
                starts_on=date(2027, 4, 1),
                ends_on=date(2027, 4, 30),
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    actions = set(
        session.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "ledger_account")
        ).all()
    )
    assert actions == {"finance.ledger_account.created"}


def test_finance_masters_are_isolated_per_firm() -> None:
    """One firm never sees another firm's chart of accounts."""
    factory = _session_factory()
    session = factory()
    first = _firm(session, "ONE")
    second = _firm(session, "TWO")
    actor_id = uuid4()
    service = FinanceService(session)
    _Book(session, first.id, actor_id)

    assert service.list_ledger_accounts(firm_id=second.id) == []
    assert service.list_financial_years(firm_id=second.id) == []
    # The same codes are free for the second firm.
    other = _Book(session, second.id, actor_id)
    assert other.cash.firm_id == second.id
    assert len(service.list_ledger_accounts(firm_id=first.id)) == 2


def test_journal_entry_requires_balance_and_open_period() -> None:
    """The engine rejects unbalanced entries and closed or foreign periods."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    with pytest.raises(ValidationError, match="not balanced"):
        engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 4, 10),
            reference_number="JV-BAD",
            description=None,
            lines=[
                JournalLineData(
                    ledger_account_id=book.cash.id, debit_amount=Decimal("100")
                ),
                JournalLineData(
                    ledger_account_id=book.sales.id, credit_amount=Decimal("90")
                ),
            ],
            actor_id=actor_id,
        )

    with pytest.raises(ValidationError, match="inside the accounting period"):
        engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 6, 1),
            reference_number="JV-DATE",
            description=None,
            lines=_sale_lines(book, "100"),
            actor_id=actor_id,
        )

    # A closed period stops accepting postings.
    period = session.get(AccountingPeriod, book.period.id)
    assert period is not None
    period.status = PeriodStatus.CLOSED.value
    session.commit()
    with pytest.raises(ValidationError, match="closed"):
        engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 4, 10),
            reference_number="JV-CLOSED",
            description=None,
            lines=_sale_lines(book, "100"),
            actor_id=actor_id,
        )


def test_journal_entries_can_be_found_and_not_only_created() -> None:
    """The module could create an entry and read one back by id, and no more.

    Everything the documents posted was unfindable unless somebody already knew
    its id, which is the same as not being there. The list is ordered by
    journal date and then reference number, so two entries on one date keep a
    stable order across pages instead of shuffling.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    other = _firm(session, code="OTHER")
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    for day, reference in ((10, "JV-002"), (10, "JV-001"), (12, "JV-003")):
        engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 4, day),
            reference_number=reference,
            description=f"Seeded {reference}",
            lines=_sale_lines(book, "100"),
            actor_id=actor_id,
        )
    session.commit()

    rows, total = engine.list_entries(firm_id=firm.id, page=1, page_size=10)
    assert total == 3
    assert [row.reference_number for row in rows] == [
        "JV-003",
        "JV-002",
        "JV-001",
    ], "newest date first, and the reference breaks a same-day tie"

    # Paging is a window on that order, not a second one.
    first, _ = engine.list_entries(firm_id=firm.id, page=1, page_size=2)
    second, _ = engine.list_entries(firm_id=firm.id, page=2, page_size=2)
    assert [row.reference_number for row in first] == ["JV-003", "JV-002"]
    assert [row.reference_number for row in second] == ["JV-001"]

    searched, found = engine.list_entries(
        firm_id=firm.id, page=1, page_size=10, search="JV-002"
    )
    assert found == 1
    assert searched[0].reference_number == "JV-002"

    drafts, draft_total = engine.list_entries(
        firm_id=firm.id, page=1, page_size=10, status="POSTED"
    )
    assert draft_total == 0, "nothing has been posted yet"
    assert drafts == []

    # Another firm's entries are not this firm's, however the list is asked.
    _, foreign = engine.list_entries(firm_id=other.id, page=1, page_size=10)
    assert foreign == 0


def test_posting_updates_balances_by_normal_side_and_is_auditable() -> None:
    """Posting writes balances that respect each account's normal side."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-0001",
        description="Cash sale",
        lines=_sale_lines(book, "150.00"),
        actor_id=actor_id,
    )
    session.commit()
    assert entry.status == JournalStatus.DRAFT.value
    assert entry.total_debit == Decimal("150.00")

    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()
    assert entry.status == JournalStatus.POSTED.value
    assert entry.posted_at is not None

    balances = {
        balance.ledger_account_id: balance
        for balance in session.scalars(select(LedgerBalance)).all()
    }
    # Cash is an asset: a debit increases it.
    assert balances[book.cash.id].closing_balance == Decimal("150.00")
    # Sales is income: a credit increases it, so the balance is also positive.
    assert balances[book.sales.id].closing_balance == Decimal("150.00")
    assert len(session.scalars(select(GLPosting)).all()) == 2

    # A posted entry cannot be posted twice.
    with pytest.raises(ValidationError, match="Only draft entries"):
        engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)

    posted_audits = session.scalars(
        select(AuditLog.action).where(AuditLog.entity_type == "journal_entry")
    ).all()
    assert "finance.journal_entry.posted" in set(posted_audits)


def test_reversal_cancels_the_original_and_zeroes_the_ledger() -> None:
    """A reversal mirrors the original entry and nets balances back to zero."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-0002",
        description="Cash sale",
        lines=_sale_lines(book, "80.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    # Only posted entries can be reversed.
    reversal = engine.reverse_entry(
        entry.id,
        firm_id=firm.id,
        reference_number="JV-0002-R",
        actor_id=actor_id,
    )
    session.commit()

    assert entry.status == JournalStatus.REVERSED.value
    assert reversal.reversal_of_id == entry.id
    assert reversal.status == JournalStatus.POSTED.value

    balances = {
        balance.ledger_account_id: balance
        for balance in session.scalars(select(LedgerBalance)).all()
    }
    assert balances[book.cash.id].closing_balance == Decimal("0.00")
    assert balances[book.sales.id].closing_balance == Decimal("0.00")

    # A reversed entry cannot be reversed again.
    with pytest.raises(ValidationError, match="Only posted entries"):
        engine.reverse_entry(
            entry.id,
            firm_id=firm.id,
            reference_number="JV-0002-R2",
            actor_id=actor_id,
        )


def test_a_quiet_period_still_lists_the_balances_it_carries() -> None:
    """A trial balance lists every account with a balance, not only the movers.

    A `ledger_balances` row is written when an account is posted to, so the
    stored rows for a period are the accounts that moved in it. Totting those up
    reported a firm out of balance whenever a quiet period touched one side and
    not the other: March 2027 in the seeded demo firm read `dr 0.00 cr
    211217.50` with the ledger perfectly sound.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    # April trades: cash and sales both move and the period balances.
    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-APR",
        description="Cash sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    may = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=book.year.id,
            period_number=2,
            code="P2",
            name="May 2026",
            starts_on=date(2026, 5, 1),
            ends_on=date(2026, 5, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()

    # Nothing at all happens in May.
    report = GeneralLedgerService(session).trial_balance(
        firm_id=firm.id, accounting_period_id=may.id
    )

    assert {line.account_code for line in report.lines} == {
        "1000",
        "4000",
    }, "both balances are carried, not only whichever account moved"
    for line in report.lines:
        assert line.period_debit == Decimal("0.00")
        assert line.period_credit == Decimal("0.00")
        assert line.opening_balance == line.closing_balance
    assert report.total_debit == Decimal("100.00")
    assert report.total_credit == Decimal("100.00")
    assert report.is_balanced, "a period where nothing happened still balances"

    # Carrying a balance into a report must not write one into the ledger: a
    # stored balance for a period nothing happened in is invented history.
    stored = session.scalars(
        select(LedgerBalance).where(LedgerBalance.accounting_period_id == may.id)
    ).all()
    assert stored == []


def test_a_statement_opens_at_the_balance_the_account_carries() -> None:
    """An account statement for a quiet period is not a statement of nothing.

    A `ledger_balances` row exists only for an account posted to in the period,
    and the statement read its opening from that row or reported zero. So an
    account that saw no movement opened at zero and closed at zero, which says
    the account is empty rather than that it was quiet -- Trade Receivables read
    `opening 0, closing 0` for March 2027 in the seeded firm while the firm was
    owed 249,236.70.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-APR",
        description="Cash sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    may = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=book.year.id,
            period_number=2,
            code="P2",
            name="May 2026",
            starts_on=date(2026, 5, 1),
            ends_on=date(2026, 5, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()

    report = GeneralLedgerService(session).general_ledger(
        firm_id=firm.id,
        ledger_account_id=book.cash.id,
        accounting_period_id=may.id,
    )

    assert report.opening_balance == Decimal("100.00"), "the balance is carried in"
    assert report.closing_balance == Decimal("100.00"), "and nothing moved it"
    assert report.lines == [], "a quiet period has no movements to show"
    assert report.total_debit == Decimal("0.00")
    assert report.total_credit == Decimal("0.00")

    # Reading a statement writes nothing, for the same reason the trial balance
    # carries its rows in memory.
    stored = session.scalars(
        select(LedgerBalance).where(LedgerBalance.accounting_period_id == may.id)
    ).all()
    assert stored == []


def test_a_statement_for_the_first_period_opens_at_nothing() -> None:
    """With no earlier period there is nothing to carry, and zero is the truth."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)

    report = GeneralLedgerService(session).general_ledger(
        firm_id=firm.id,
        ledger_account_id=book.cash.id,
        accounting_period_id=book.period.id,
    )

    assert report.opening_balance == Decimal("0.00")
    assert report.closing_balance == Decimal("0.00")
    assert report.lines == []


def _expense_account(
    session: Session, book: _Book, firm_id: UUID, actor_id: UUID, code: str, name: str
) -> LedgerAccount:
    """Create one expense account under its own group."""
    service = FinanceService(session)
    group = service.create_account_group(
        AccountGroupCreate(
            code=f"EXP{code}",
            name=f"{name} group",
            account_type=AccountTypeEnum.EXPENSE,
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    return service.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=group.id,
            code=code,
            name=name,
            account_type=AccountTypeEnum.EXPENSE,
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )


def test_the_balance_sheet_balances_because_earnings_are_carried_to_equity() -> None:
    """Nothing closes the year, so the accumulated result is the equity.

    Income and expense accounts here accumulate indefinitely -- no year-end
    entry ever zeroes them -- so their net is the firm's earnings. Without
    carrying that into equity the sheet is short by everything the firm has
    ever made, and no chart of accounts can fix it because the entry that would
    do it is never written. March 2027 in the seeded firm balances to the rupee
    this way: assets 484,890.29 against liabilities 393,759.20 and an
    accumulated result of 91,131.09.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    # A sale of 100 for cash: cash 100 on one side, sales 100 on the other, and
    # nothing in equity to hold the profit.
    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-SALE",
        description="Cash sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    report = GeneralLedgerService(session).balance_sheet(
        firm_id=firm.id, accounting_period_id=book.period.id
    )

    assert [line.account_code for line in report.assets] == ["1000"]
    assert report.total_assets == Decimal("100.00")
    assert report.liabilities == []
    assert report.equity == [], "the seeded chart has no equity account at all"
    assert report.total_equity == Decimal("100.00"), "the result is the equity"
    assert report.result_for_the_year == Decimal("100.00")
    assert report.retained_earnings_brought_forward == Decimal("0.00")
    assert report.is_balanced

    # Sales is an income account and has no business appearing as an asset or
    # a liability, however the earnings are carried.
    listed = {
        line.account_code for line in report.assets + report.liabilities + report.equity
    }
    assert "4000" not in listed


def test_the_balance_sheet_splits_this_year_from_what_came_before() -> None:
    """Two figures, because they answer different questions.

    What the firm built up before this year, and how this year is going. Their
    sum is the whole accumulated result.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-LAST-YEAR",
        description="Last year's sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    next_year = service.create_financial_year(
        FinancialYearCreate(
            code="FY2028",
            name="2027-2028",
            starts_on=date(2027, 4, 1),
            ends_on=date(2028, 3, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    april = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=next_year.id,
            period_number=1,
            code="P1",
            name="April 2027",
            starts_on=date(2027, 4, 1),
            ends_on=date(2027, 4, 30),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()
    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=april.id,
        journal_date=date(2027, 4, 10),
        reference_number="JV-THIS-YEAR",
        description="This year's sale",
        lines=_sale_lines(book, "40.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    report = GeneralLedgerService(session).balance_sheet(
        firm_id=firm.id, accounting_period_id=april.id
    )

    assert report.retained_earnings_brought_forward == Decimal("100.00")
    assert report.result_for_the_year == Decimal("40.00")
    assert report.total_equity == Decimal("140.00")
    assert report.total_assets == Decimal("140.00")
    assert report.is_balanced


def test_a_balance_sheet_carries_an_account_that_did_not_move() -> None:
    """As at, not for: a quiet account still holds what it holds.

    The same omission that made the trial balance report a sound ledger out of
    balance would take an asset off the balance sheet entirely.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-SALE",
        description="Cash sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    may = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=book.year.id,
            period_number=2,
            code="P2",
            name="May 2026",
            starts_on=date(2026, 5, 1),
            ends_on=date(2026, 5, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()

    report = GeneralLedgerService(session).balance_sheet(
        firm_id=firm.id, accounting_period_id=may.id
    )

    assert [line.amount for line in report.assets] == [
        Decimal("100.00")
    ], "cash saw nothing in May and still holds what April left it"
    assert report.total_equity == Decimal("100.00")
    assert report.result_for_the_year == Decimal("100.00"), (
        "the result is the year to this period, not the period: April is in "
        "the same financial year"
    )
    assert report.retained_earnings_brought_forward == Decimal("0.00")
    assert report.is_balanced


def test_the_profit_and_loss_reports_the_month_and_the_year_to_date() -> None:
    """One column is the wrong answer half the time.

    A month is what somebody asks about; the year to date is what tells them
    whether the month was normal. An account that saw nothing this month but
    moved earlier in the year belongs in the report for its year-to-date figure
    alone -- it is part of the year's result.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)
    rent = _expense_account(session, book, firm.id, actor_id, "6000", "Rent")

    def post(
        period_id: UUID, when: date, reference: str, lines: list[JournalLineData]
    ) -> None:
        entry = engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=period_id,
            journal_date=when,
            reference_number=reference,
            description=reference,
            lines=lines,
            actor_id=actor_id,
        )
        engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
        session.commit()

    # April: a sale of 100 and rent of 40.
    post(book.period.id, date(2026, 4, 10), "JV-SALE", _sale_lines(book, "100.00"))
    post(
        book.period.id,
        date(2026, 4, 20),
        "JV-RENT",
        [
            JournalLineData(ledger_account_id=rent.id, debit_amount=Decimal("40.00")),
            JournalLineData(
                ledger_account_id=book.cash.id, credit_amount=Decimal("40.00")
            ),
        ],
    )

    may = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=book.year.id,
            period_number=2,
            code="P2",
            name="May 2026",
            starts_on=date(2026, 5, 1),
            ends_on=date(2026, 5, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()
    # May: a sale of 60 and no rent.
    post(may.id, date(2026, 5, 12), "JV-SALE-2", _sale_lines(book, "60.00"))

    report = GeneralLedgerService(session).profit_and_loss(
        firm_id=firm.id, accounting_period_id=may.id
    )

    assert [line.account_code for line in report.income] == ["4000"]
    assert report.income[0].period_amount == Decimal("60.00")
    assert report.income[0].year_to_date_amount == Decimal("160.00")

    assert [line.account_code for line in report.expenses] == ["6000"], (
        "rent moved earlier in the year, so it is part of this year's result "
        "even though it saw nothing this month"
    )
    assert report.expenses[0].period_amount == Decimal("0.00")
    assert report.expenses[0].year_to_date_amount == Decimal("40.00")

    assert report.total_income == Decimal("60.00")
    assert report.total_expense == Decimal("0.00")
    assert report.net_profit == Decimal("60.00")
    assert report.year_to_date_income == Decimal("160.00")
    assert report.year_to_date_expense == Decimal("40.00")
    assert report.year_to_date_net_profit == Decimal("120.00")
    assert report.financial_year_id == book.year.id


def test_the_profit_and_loss_stops_at_the_financial_year() -> None:
    """Profit resets at the year, so the year to date starts there.

    Carrying last year's trading into this year's result would overstate it by
    everything the firm has ever done.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-LAST-YEAR",
        description="Last year's sale",
        lines=_sale_lines(book, "100.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    next_year = service.create_financial_year(
        FinancialYearCreate(
            code="FY2028",
            name="2027-2028",
            starts_on=date(2027, 4, 1),
            ends_on=date(2028, 3, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    april = service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=next_year.id,
            period_number=1,
            code="P1",
            name="April 2027",
            starts_on=date(2027, 4, 1),
            ends_on=date(2027, 4, 30),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()

    report = GeneralLedgerService(session).profit_and_loss(
        firm_id=firm.id, accounting_period_id=april.id
    )

    assert report.income == [], "last year's sale is not this year's income"
    assert report.year_to_date_income == Decimal("0.00")
    assert report.net_profit == Decimal("0.00")


def test_a_contra_income_account_reduces_income_rather_than_being_a_cost() -> None:
    """A sales return is negative income, not an expense.

    Both figures are the account's movement in its natural direction, so an
    income account that ran the other way reports negative -- which is what it
    does to the result. Filing it as a cost would report the same net profit
    with revenue and costs both overstated.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)
    engine = JournalEntryEngine(session)

    returns = service.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=book.income_group.id,
            code="4100",
            name="Sales Returns",
            account_type=AccountTypeEnum.INCOME,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-RETURN",
        description="Goods returned",
        lines=[
            JournalLineData(
                ledger_account_id=returns.id, debit_amount=Decimal("25.00")
            ),
            JournalLineData(
                ledger_account_id=book.cash.id, credit_amount=Decimal("25.00")
            ),
        ],
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    report = GeneralLedgerService(session).profit_and_loss(
        firm_id=firm.id, accounting_period_id=book.period.id
    )

    assert [line.account_code for line in report.income] == ["4100"]
    assert report.income[0].period_amount == Decimal("-25.00")
    assert report.expenses == []
    assert report.net_profit == Decimal("-25.00")


def test_an_income_account_is_a_profit_and_loss_account_without_being_told() -> None:
    """The flags follow the account type unless the caller says otherwise.

    They were plain defaults of `True` / `False` that nothing set, so every
    account the chart-of-accounts seeder built claimed to be a balance sheet
    account and no part of the profit and loss -- Sales and Purchases included,
    which the account detail panel showed to the user as fact.
    """
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)

    assert book.sales.is_profit_loss is True
    assert book.sales.is_balance_sheet is False
    assert book.cash.is_balance_sheet is True
    assert book.cash.is_profit_loss is False

    # And an administrator can still overrule it: a memo account belongs
    # wherever they decide it does.
    memo_group = service.create_account_group(
        AccountGroupCreate(
            code="MEMO", name="Memoranda", account_type=AccountTypeEnum.INCOME
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    off_statement = service.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=memo_group.id,
            code="4900",
            name="Kept off the statement",
            account_type=AccountTypeEnum.INCOME,
            is_profit_loss=False,
            is_balance_sheet=True,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert off_statement.is_profit_loss is False
    assert off_statement.is_balance_sheet is True


def test_an_account_with_nothing_to_carry_is_left_out() -> None:
    """A trial balance is not a list of every account ever created."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)

    unused = service.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=book.asset_group.id,
            code="1999",
            name="Never Used",
            account_type=AccountTypeEnum.ASSET,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    engine = JournalEntryEngine(session)
    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-APR2",
        description=None,
        lines=_sale_lines(book, "50.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    report = GeneralLedgerService(session).trial_balance(
        firm_id=firm.id, accounting_period_id=book.period.id
    )

    assert unused.code not in {line.account_code for line in report.lines}
    assert report.is_balanced


def test_trial_balance_reports_both_sides_and_balances() -> None:
    """The trial balance splits closing balances onto their normal sides."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-0003",
        description="Cash sale",
        lines=_sale_lines(book, "250.00"),
        actor_id=actor_id,
    )
    engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
    session.commit()

    report = GeneralLedgerService(session).trial_balance(
        firm_id=firm.id, accounting_period_id=book.period.id
    )
    assert report.is_balanced
    assert report.total_debit == Decimal("250.00")
    assert report.total_credit == Decimal("250.00")
    assert {line.account_code for line in report.lines} == {"1000", "4000"}

    statement = GeneralLedgerService(session).general_ledger(
        firm_id=firm.id,
        ledger_account_id=book.cash.id,
        accounting_period_id=book.period.id,
    )
    assert statement.closing_balance == Decimal("250.00")
    assert len(statement.lines) == 1
    assert statement.lines[0].running_balance == Decimal("250.00")

    with pytest.raises(ResourceNotFoundError):
        GeneralLedgerService(session).general_ledger(
            firm_id=firm.id,
            ledger_account_id=uuid4(),
            accounting_period_id=book.period.id,
        )


def test_finance_api_scope_enforces_membership_and_permissions() -> None:
    """API routes require an active firm membership and the right permission."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    outsider_firm = _firm(session, "OTHER")
    user_id = uuid4()
    book = _Book(session, firm.id, user_id)
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    permissions = {"JOURNAL_CREATE", "JOURNAL_POST", "TRIAL_BALANCE_VIEW"}
    principal = _principal(user_id, permissions)

    # A missing firm header is refused.
    with pytest.raises(AuthorizationError, match="X-Firm-ID is required"):
        _firm_scope(principal, session, None)

    # A firm the user does not belong to is refused.
    with pytest.raises(AuthorizationError, match="not authorized"):
        _firm_scope(principal, session, outsider_firm.id)

    scope = _firm_scope(principal, session, firm.id)
    assert scope.firm_id == firm.id
    assert scope.actor_id == user_id

    created = create_journal_entry(
        JournalEntryCreate(
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 4, 12),
            reference_number="JV-API-1",
            description="API entry",
            lines=[
                {
                    "ledger_account_id": book.cash.id,
                    "debit_amount": "40.00",
                },
                {
                    "ledger_account_id": book.sales.id,
                    "credit_amount": "40.00",
                },
            ],
        ),
        scope,
        session,
    )
    assert created.data.reference_number == "JV-API-1"
    assert created.data.status == JournalStatus.DRAFT.value

    posted = post_journal_entry(created.data.id, scope, session)
    assert posted.data.status == JournalStatus.POSTED.value

    report = trial_balance(book.period.id, scope, session)
    assert report.data.is_balanced
    assert report.data.total_debit == Decimal("40.00")


def test_journal_line_schema_rejects_two_sided_and_empty_lines() -> None:
    """A journal line must carry exactly one of debit or credit."""
    common = {
        "journal_type_id": uuid4(),
        "voucher_type_id": uuid4(),
        "accounting_period_id": uuid4(),
        "journal_date": date(2026, 4, 1),
        "reference_number": "JV-X",
    }
    with pytest.raises(ValueError, match="both a debit and a credit"):
        JournalEntryCreate(
            **common,
            lines=[
                {
                    "ledger_account_id": uuid4(),
                    "debit_amount": "10",
                    "credit_amount": "10",
                },
                {"ledger_account_id": uuid4(), "credit_amount": "10"},
            ],
        )
    with pytest.raises(ValueError, match="must carry a debit or a credit"):
        JournalEntryCreate(
            **common,
            lines=[
                {"ledger_account_id": uuid4()},
                {"ledger_account_id": uuid4(), "credit_amount": "10"},
            ],
        )
    with pytest.raises(ValueError, match="not balanced"):
        JournalEntryCreate(
            **common,
            lines=[
                {"ledger_account_id": uuid4(), "debit_amount": "10"},
                {"ledger_account_id": uuid4(), "credit_amount": "9"},
            ],
        )


def test_locked_period_accepts_only_a_reopen() -> None:
    """A locked period rejects edits but can still be reopened."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    service = FinanceService(session)

    service.update_accounting_period(
        book.period.id,
        AccountingPeriodUpdate(status=PeriodStatusEnum.LOCKED),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError, match="can only be reopened"):
        service.update_accounting_period(
            book.period.id,
            AccountingPeriodUpdate(name="Renamed while locked"),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    with pytest.raises(ValidationError, match="can only be reopened"):
        service.update_accounting_period(
            book.period.id,
            AccountingPeriodUpdate(status=PeriodStatusEnum.CLOSED),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    reopened = service.update_accounting_period(
        book.period.id,
        AccountingPeriodUpdate(status=PeriodStatusEnum.OPEN),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert reopened.status == PeriodStatus.OPEN.value


def test_control_accounts_map_posting_purposes_to_nominated_accounts() -> None:
    """A firm nominates where each kind of posting lands, and the map is checked.

    Automatic GL posting never existed, and the consumer that once guessed
    accounts by matching on their name was removed for good reason. Posting
    rules belong in code; which account they land in belongs to the firm.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm_id=firm.id, actor_id=actor_id)
    service = ControlAccountService(session)

    # Nothing is mapped, and the error names what is missing rather than
    # falling back to a guess.
    with pytest.raises(ValidationError) as unmapped:
        service.resolve(firm.id, ControlAccountPurpose.SALES_REVENUE)
    assert "SALES_REVENUE" in str(unmapped.value)

    service.assign(
        firm.id,
        ControlAccountPurpose.SALES_REVENUE,
        book.sales.id,
        actor_id=actor_id,
    )
    assert (
        service.resolve(firm.id, ControlAccountPurpose.SALES_REVENUE) == book.sales.id
    )

    # Re-assigning replaces rather than duplicating; the unique constraint on
    # (firm, purpose) means a second row would fail outright.
    service.assign(firm.id, ControlAccountPurpose.CASH, book.cash.id, actor_id=actor_id)
    service.assign(firm.id, ControlAccountPurpose.CASH, book.cash.id, actor_id=actor_id)
    assert len(service.mapping(firm.id)) == 2

    # Revenue cannot be pointed at an asset account.
    with pytest.raises(ValidationError) as wrong_type:
        service.assign(
            firm.id,
            ControlAccountPurpose.SALES_REVENUE,
            book.cash.id,
            actor_id=actor_id,
        )
    assert "INCOME" in str(wrong_type.value)

    # And every remaining gap can be reported at once.
    gaps = service.missing(
        firm.id,
        (
            ControlAccountPurpose.SALES_REVENUE,
            ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
            ControlAccountPurpose.OUTPUT_TAX,
        ),
    )
    assert gaps == (
        ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
        ControlAccountPurpose.OUTPUT_TAX,
    )


def test_sales_invoice_posts_receivable_revenue_and_tax() -> None:
    """An approved invoice becomes a balanced journal, or is refused.

    Finance was an island: no module outside app/finance imported it, so the
    trial balance could only ever reflect hand-keyed journals.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm_id=firm.id, actor_id=actor_id)
    finance = FinanceService(session)
    receivable = finance.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=book.asset_group.id,
            code="1100",
            name="Trade Receivables",
            account_type=AccountTypeEnum.ASSET,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    tax_group = finance.create_account_group(
        AccountGroupCreate(
            code="DUT", name="Duties", account_type=AccountTypeEnum.LIABILITY
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    output_tax = finance.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=tax_group.id,
            code="2200",
            name="Output Tax",
            account_type=AccountTypeEnum.LIABILITY,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    posting = DocumentPostingService(session)
    invoice_id = uuid4()

    # Nothing mapped yet: the post is refused and names every gap at once.
    with pytest.raises(ValidationError) as unmapped:
        posting.post_sales_invoice(
            firm_id=firm.id,
            invoice_id=invoice_id,
            invoice_number="SI-1",
            invoice_date=date(2026, 4, 15),
            taxable_amount=Decimal("1000"),
            tax_amount=Decimal("180"),
            total_amount=Decimal("1180"),
            actor_id=actor_id,
        )
    message = str(unmapped.value)
    assert "ACCOUNTS_RECEIVABLE" in message
    assert "SALES_REVENUE" in message
    assert "OUTPUT_TAX" in message

    controls = ControlAccountService(session)
    controls.assign(
        firm.id,
        ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
        receivable.id,
        actor_id=actor_id,
    )
    controls.assign(
        firm.id, ControlAccountPurpose.SALES_REVENUE, book.sales.id, actor_id=actor_id
    )
    controls.assign(
        firm.id, ControlAccountPurpose.OUTPUT_TAX, output_tax.id, actor_id=actor_id
    )

    entry = posting.post_sales_invoice(
        firm_id=firm.id,
        invoice_id=invoice_id,
        invoice_number="SI-1",
        invoice_date=date(2026, 4, 15),
        taxable_amount=Decimal("1000"),
        tax_amount=Decimal("180"),
        total_amount=Decimal("1180"),
        actor_id=actor_id,
    )
    assert entry.status == JournalStatus.POSTED.value
    assert entry.source_module == "sales_invoice"
    assert entry.source_id == invoice_id
    legs = {
        line.ledger_account_id: (line.debit_amount, line.credit_amount)
        for line in session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        ).all()
    }
    assert legs[receivable.id][0] == Decimal("1180.00")
    assert legs[book.sales.id][1] == Decimal("1000.00")
    assert legs[output_tax.id][1] == Decimal("180.00")

    # A date no open period covers refuses the post rather than skipping it.
    with pytest.raises(ValidationError) as closed:
        posting.post_sales_invoice(
            firm_id=firm.id,
            invoice_id=uuid4(),
            invoice_number="SI-2",
            invoice_date=date(2027, 1, 5),
            taxable_amount=Decimal("100"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("100"),
            actor_id=actor_id,
        )
    assert "No open accounting period" in str(closed.value)


def test_seed_finance_setup_is_complete_and_idempotent() -> None:
    """A seeded firm can post, and re-seeding changes nothing.

    The sample firms had no chart of accounts, no periods and no journal types
    at all, so DocumentPostingService — which refuses rather than guesses — had
    nothing to post against.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()

    created = seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    assert created["accounts"] == len(CHART)
    assert created["periods"] == 12
    assert created["mappings"] == sum(1 for entry in CHART if entry.purpose)

    # Every purpose the sales-invoice posting needs is now mapped.
    posting = DocumentPostingService(session)
    entry = posting.post_sales_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="SI-SEED",
        invoice_date=date(2026, 8, 4),
        taxable_amount=Decimal("1000"),
        tax_amount=Decimal("180"),
        total_amount=Decimal("1180"),
        actor_id=actor_id,
    )
    assert entry.status == JournalStatus.POSTED.value

    # Re-running creates nothing: the seed is safe after a partial failure or a
    # tenancy rebuild.
    again = seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    assert again == {
        "groups": 0,
        "accounts": 0,
        "periods": 0,
        "mappings": 0,
        "types": 0,
    }


def test_a_conflict_leaves_earlier_work_in_the_transaction() -> None:
    """A duplicate key rolls back the clashing row, not the caller's work.

    FinanceService used to commit after every operation, so its rollback-on-
    conflict only ever discarded the failed insert. Once the router owns the
    transaction that same rollback would throw away everything done since the
    last commit — a financial year created moments earlier would vanish because
    an unrelated cost centre clashed.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = FinanceService(session)

    year = service.create_financial_year(
        FinancialYearCreate(
            code="FY2026",
            name="Financial Year 2026-2027",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.create_cost_center(
        CostCenterCreate(code="CC1", name="First"),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    with pytest.raises(ConflictError):
        service.create_cost_center(
            CostCenterCreate(code="CC1", name="Duplicate"),
            firm_id=firm.id,
            actor_id=actor_id,
        )

    # The year and the first cost centre survive the conflict.
    assert (
        session.scalar(select(FinancialYear.id).where(FinancialYear.id == year.id))
        is not None
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(CostCenter)
            .where(CostCenter.firm_id == firm.id, CostCenter.is_deleted.is_(False))
        )
        == 1
    )
    # And the session is still usable rather than needing a rollback.
    service.create_cost_center(
        CostCenterCreate(code="CC2", name="After the conflict"),
        firm_id=firm.id,
        actor_id=actor_id,
    )


def test_goods_issue_posts_cost_of_goods_sold_against_inventory() -> None:
    """Dispatched stock moves its cost from inventory into expense.

    The amount comes from what the stock ledger released at the moving average,
    not from the selling price on the invoice — which is why inventory had to be
    given a cost before any of this could mean anything.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    posting = DocumentPostingService(session)
    note_id = uuid4()

    entry = posting.post_goods_issue(
        firm_id=firm.id,
        document_id=note_id,
        document_number="DN-1",
        issue_date=date(2026, 8, 5),
        cost_amount=Decimal("550"),
        source_module="delivery_note",
        actor_id=actor_id,
    )
    assert entry is not None
    assert entry.status == JournalStatus.POSTED.value
    assert entry.source_module == "delivery_note"

    accounts = ControlAccountService(session).mapping(firm.id)
    legs = {
        line.ledger_account_id: (line.debit_amount, line.credit_amount)
        for line in session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        ).all()
    }
    cogs = accounts[ControlAccountPurpose.COST_OF_GOODS_SOLD.value]
    inventory = accounts[ControlAccountPurpose.INVENTORY.value]
    assert legs[cogs][0] == Decimal("550.00"), "cost of goods sold is debited"
    assert legs[inventory][1] == Decimal("550.00"), "inventory is credited"

    # Stock carrying no cost — received before valuation existed — writes no
    # journal rather than an empty one.
    assert (
        posting.post_goods_issue(
            firm_id=firm.id,
            document_id=uuid4(),
            document_number="DN-2",
            issue_date=date(2026, 8, 5),
            cost_amount=Decimal("0"),
            source_module="delivery_note",
            actor_id=actor_id,
        )
        is None
    )


def test_receipt_accrual_is_raised_then_cleared_by_the_supplier_invoice() -> None:
    """Stock arrives before its invoice, so the liability moves in two steps.

    Receipts posted nothing at all until now: inventory was only ever credited
    by dispatches, so the account drove negative while the warehouse filled up.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    posting = DocumentPostingService(session)
    accounts = ControlAccountService(session).mapping(firm.id)
    inventory = accounts[ControlAccountPurpose.INVENTORY.value]
    accrual = accounts[ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED.value]
    input_tax = accounts[ControlAccountPurpose.INPUT_TAX.value]
    payables = accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE.value]

    def _legs(entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        return {
            line.ledger_account_id: (line.debit_amount, line.credit_amount)
            for line in session.scalars(
                select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
            ).all()
        }

    receipt = posting.post_goods_receipt(
        firm_id=firm.id,
        document_id=uuid4(),
        document_number="GRN-1",
        receipt_date=date(2026, 8, 4),
        cost_amount=Decimal("1000"),
        actor_id=actor_id,
    )
    assert receipt is not None
    receipt_legs = _legs(receipt.id)
    assert receipt_legs[inventory][0] == Decimal("1000.00"), "stock is capitalised"
    assert receipt_legs[accrual][1] == Decimal("1000.00"), "the accrual is raised"

    invoice = posting.post_purchase_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="PI-1",
        invoice_date=date(2026, 8, 6),
        goods_amount=Decimal("1000"),
        tax_amount=Decimal("180"),
        total_amount=Decimal("1180"),
        actor_id=actor_id,
    )
    invoice_legs = _legs(invoice.id)
    assert invoice_legs[accrual][0] == Decimal("1000.00"), "the accrual is cleared"
    assert invoice_legs[input_tax][0] == Decimal("180.00")
    assert invoice_legs[payables][1] == Decimal("1180.00")
    # Inventory is untouched by the invoice: it was valued at what the receipt
    # cost, and re-valuing here would double-count.
    assert inventory not in invoice_legs

    # A receipt that brought in no value writes nothing.
    assert (
        posting.post_goods_receipt(
            firm_id=firm.id,
            document_id=uuid4(),
            document_number="GRN-2",
            receipt_date=date(2026, 8, 4),
            cost_amount=Decimal("0"),
            actor_id=actor_id,
        )
        is None
    )


def test_a_supplier_price_change_lands_in_purchase_price_variance() -> None:
    """The accrual clears at cost; the difference reaches the P&L.

    Clearing at the invoice price instead would leave the gap sitting in goods
    received not invoiced, growing quietly and explaining nothing.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    posting = DocumentPostingService(session)
    accounts = ControlAccountService(session).mapping(firm.id)
    accrual = accounts[ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED.value]
    variance = accounts[ControlAccountPurpose.PURCHASE_PRICE_VARIANCE.value]
    payables = accounts[ControlAccountPurpose.ACCOUNTS_PAYABLE.value]

    def _legs(entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        return {
            line.ledger_account_id: (line.debit_amount, line.credit_amount)
            for line in session.scalars(
                select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
            ).all()
        }

    # Received at 1000, billed 1050: an unfavourable variance of 50.
    dearer = posting.post_purchase_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="PI-DEAR",
        invoice_date=date(2026, 8, 6),
        goods_amount=Decimal("1050"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("1050"),
        accrued_amount=Decimal("1000"),
        actor_id=actor_id,
    )
    legs = _legs(dearer.id)
    assert legs[accrual][0] == Decimal("1000.00"), "the accrual clears at cost"
    assert legs[variance][0] == Decimal("50.00"), "the overspend is an expense"
    assert legs[payables][1] == Decimal("1050.00"), "the supplier is owed the bill"

    # Received at 1000, billed 900: a favourable variance, credited.
    cheaper = posting.post_purchase_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="PI-CHEAP",
        invoice_date=date(2026, 8, 6),
        goods_amount=Decimal("900"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("900"),
        accrued_amount=Decimal("1000"),
        actor_id=actor_id,
    )
    legs = _legs(cheaper.id)
    assert legs[accrual][0] == Decimal("1000.00")
    assert legs[variance][1] == Decimal("100.00"), "the saving is a credit"
    assert legs[payables][1] == Decimal("900.00")

    # Invoice matching the receipt raises no variance line at all.
    exact = posting.post_purchase_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="PI-EXACT",
        invoice_date=date(2026, 8, 6),
        goods_amount=Decimal("1000"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("1000"),
        accrued_amount=Decimal("1000"),
        actor_id=actor_id,
    )
    assert variance not in _legs(exact.id)


def _engine_book() -> tuple[Session, UUID, UUID, _Book]:
    """Build one firm with the masters a journal needs."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    return session, firm.id, actor, _Book(session, firm.id, actor)


def test_a_journal_entry_cannot_be_stored_with_lines_that_do_not_balance() -> None:
    """The check must run on the values that get stored, not on their sum.

    Legs of 100.0100 against 100.0050 + 0.0050 balance exactly at four
    decimals. Rounded to the ledger's two they become 100.01 against
    100.01 + 0.01. The old check summed first and rounded after, saw 100.01 on
    both sides, and wrote an entry whose lines were a cent apart with
    ``is_balanced`` true -- and ``_post_line`` copies line amounts straight
    into the general ledger, so the trial balance carried the cent forever.
    """
    session, firm_id, actor, book = _engine_book()
    engine = JournalEntryEngine(session)

    with pytest.raises(ValidationError) as error:
        engine.create_entry(
            firm_id=firm_id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=date(2026, 4, 10),
            reference_number="JV-ROUND",
            description="Rounding",
            lines=[
                JournalLineData(
                    ledger_account_id=book.cash.id, debit_amount=Decimal("100.0100")
                ),
                JournalLineData(
                    ledger_account_id=book.sales.id, credit_amount=Decimal("100.0050")
                ),
                JournalLineData(
                    ledger_account_id=book.sales.id, credit_amount=Decimal("0.0050")
                ),
            ],
            actor_id=actor,
        )

    assert "not balanced" in str(error.value)
    assert "100.02" in str(error.value), "the message must show the stored totals"


def test_every_stored_journal_entry_has_lines_that_sum_to_its_header() -> None:
    """The header totals are only trustworthy if the lines produce them."""
    session, firm_id, actor, book = _engine_book()

    entry = JournalEntryEngine(session).create_entry(
        firm_id=firm_id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-SUM",
        description="Balanced",
        lines=_sale_lines(book, "250.5550"),
        actor_id=actor,
    )
    session.commit()

    assert sum(line.debit_amount for line in entry.lines) == entry.total_debit
    assert sum(line.credit_amount for line in entry.lines) == entry.total_credit
    assert entry.total_debit == entry.total_credit


def test_a_sales_invoice_that_rounds_awkwardly_still_posts_and_balances() -> None:
    """The engine's stricter check must not start refusing real invoices.

    A document is consistent at its own four decimals; the ledger holds two.
    The poster derives the revenue leg from the total and the tax so the three
    legs still agree once rounded, rather than rounding each independently.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor
    )
    session.commit()

    entry = DocumentPostingService(session).post_sales_invoice(
        firm_id=firm.id,
        invoice_id=uuid4(),
        invoice_number="SI-ROUND",
        invoice_date=date(2026, 4, 10),
        taxable_amount=Decimal("100.0050"),
        tax_amount=Decimal("0.0050"),
        total_amount=Decimal("100.0100"),
        actor_id=actor,
    )
    session.commit()

    assert entry.status == JournalStatus.POSTED.value
    debit = sum(line.debit_amount for line in entry.lines)
    credit = sum(line.credit_amount for line in entry.lines)
    assert debit == credit == Decimal("100.01")


def test_a_movement_worth_less_than_a_cent_posts_nothing_rather_than_failing() -> None:
    """Sub-cent cost is nothing in the ledger, and nothing is not an error.

    Rounding at the document's four decimals made 0.0040 non-zero, so it
    reached the engine as a journal whose two legs both round to nil -- which
    the engine rejects, failing the dispatch that raised it.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor
    )
    session.commit()

    posted = DocumentPostingService(session).post_goods_issue(
        firm_id=firm.id,
        document_id=uuid4(),
        document_number="DN-TINY",
        issue_date=date(2026, 4, 10),
        cost_amount=Decimal("0.0040"),
        source_module="delivery_note",
        actor_id=actor,
    )

    assert posted is None


def test_the_ledger_statement_is_dated_and_ordered_by_the_journal_date() -> None:
    """A statement records when business happened, not when someone posted.

    Both entries are posted in the same run, so their ``posting_date`` wall
    clocks are effectively identical and cannot order anything. The later
    entry is deliberately created first.
    """
    session, firm_id, actor, book = _engine_book()
    engine = JournalEntryEngine(session)

    for reference, on in (
        ("JV-LATE", date(2026, 4, 20)),
        ("JV-EARLY", date(2026, 4, 2)),
    ):
        entry = engine.create_entry(
            firm_id=firm_id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=book.period.id,
            journal_date=on,
            reference_number=reference,
            description=f"Entry {reference}",
            lines=_sale_lines(book, "100.00"),
            actor_id=actor,
        )
        engine.post_entry(entry.id, firm_id=firm_id, actor_id=actor)
    session.commit()

    report = GeneralLedgerService(session).general_ledger(
        firm_id=firm_id,
        ledger_account_id=book.cash.id,
        accounting_period_id=book.period.id,
    )

    assert [line.journal_date for line in report.lines] == [
        date(2026, 4, 2),
        date(2026, 4, 20),
    ]
    assert [line.reference_number for line in report.lines] == ["JV-EARLY", "JV-LATE"]


def test_the_ledger_statement_shows_the_line_narration_it_was_given() -> None:
    """A narration typed on every line was collected and never displayed."""
    session, firm_id, actor, book = _engine_book()
    engine = JournalEntryEngine(session)

    entry = engine.create_entry(
        firm_id=firm_id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-NARR",
        description="Entry level description",
        lines=[
            JournalLineData(
                ledger_account_id=book.cash.id,
                debit_amount=Decimal("100.00"),
                description="Cash from Vijaya Super Stores",
            ),
            JournalLineData(
                ledger_account_id=book.sales.id, credit_amount=Decimal("100.00")
            ),
        ],
        actor_id=actor,
    )
    engine.post_entry(entry.id, firm_id=firm_id, actor_id=actor)
    session.commit()

    report = GeneralLedgerService(session).general_ledger(
        firm_id=firm_id,
        ledger_account_id=book.cash.id,
        accounting_period_id=book.period.id,
    )

    assert report.lines[0].description == "Cash from Vijaya Super Stores"


def test_reversing_a_returned_goods_cost_uses_what_the_movement_removed() -> None:
    """The goods leave at today's average, not the one they arrived at.

    A completed sales return brings stock in at the average of that day and
    posts it. Cancelling sends the goods back out at whatever the average is
    then -- a different number the moment anything else has been received --
    and mirroring the original entry credits inventory with a figure no
    movement removed.

    Found on 2026-08-22 by completing a return on a seeded store, receiving
    twenty units at four times the price, and cancelling: the books parted by
    16.45. It is the third of the same family, after `goods_receipt` and
    `purchase_return` the same day.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor
    )
    session.commit()
    posting = DocumentPostingService(session)
    document_id = uuid4()

    came_in = posting.post_goods_return_to_stock(
        firm_id=firm.id,
        document_id=document_id,
        document_number="SR-AVG",
        return_date=date(2026, 4, 10),
        cost_amount=Decimal("400.00"),
        source_module="sales_return",
        actor_id=actor,
    )
    assert came_in is not None

    # The average has moved since; the movement out is worth less.
    reversal = posting.reverse_goods_return_to_stock(
        firm_id=firm.id,
        entry_id=came_in.id,
        document_number="SR-AVG",
        stock_value=Decimal("250.00"),
        actor_id=actor,
    )

    assert reversal.reversal_of_id == came_in.id
    assert reversal.total_debit == reversal.total_credit == Decimal("250.00")
    inventory_leg = next(
        line for line in reversal.lines if line.credit_amount == Decimal("250.00")
    )
    assert inventory_leg.credit_amount == Decimal("250.00"), (
        "inventory is credited with what left the shelf, not the 400.00 that " "arrived"
    )
    # Both legs are the same figure, so the difference stays in cost of goods
    # sold and no third account is needed.
    assert len(reversal.lines) == 2
