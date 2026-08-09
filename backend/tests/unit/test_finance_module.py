"""Finance master, journal posting, reporting, and API scope tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
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
    GLPosting,
    JournalLine,
    JournalStatus,
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
