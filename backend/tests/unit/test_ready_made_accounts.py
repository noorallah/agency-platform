"""Petty Cash, Capital, Drawings, Transport and Fuel in every firm's books.

Backlog 106 (the first customer's list, S1). A new firm opens with the five;
an existing firm is given only the ones it lacks, by opening its books again
or by migration ``20261012_0355``, and nothing it already has is touched.
"""

import sqlite3
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contra.schemas import MoneyAccountKindEnum
from app.contra.services.contra_service import ContraVoucherService
from app.core.database.base import Base
from app.finance.models import AccountGroup, FirmControlAccount, LedgerAccount
from app.finance.services.books_register import BooksRegisterService
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm

#: name -> (number, account type, group code) as a new firm gets them.
_READY_MADE = {
    "Petty Cash": ("1005", "ASSET", "CA-CASH"),
    "Capital": ("3200", "EQUITY", "EQ"),
    "Drawings": ("3100", "EQUITY", "EQ"),
    "Transport": ("6450", "EXPENSE", "IEXP"),
    "Fuel": ("6460", "EXPENSE", "IEXP"),
}
#: The four that came with backlog 106; Drawings was there before.
_NEW = ("Petty Cash", "Capital", "Transport", "Fuel")


def _engine() -> Engine:
    """Create one shared in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _opened_firm(session: Session, code: str = "ACME") -> tuple[Firm, UUID]:
    """Create a firm and open its books; return it and the acting user."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    actor_id = uuid4()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    session.commit()
    return firm, actor_id


def _accounts(session: Session, firm_id: UUID) -> dict[str, list[LedgerAccount]]:
    """Return the firm's live accounts, keyed by name."""
    found: dict[str, list[LedgerAccount]] = {}
    for row in session.scalars(
        select(LedgerAccount).where(
            LedgerAccount.firm_id == firm_id, LedgerAccount.is_deleted.is_(False)
        )
    ):
        found.setdefault(row.name, []).append(row)
    return found


def _group_code(session: Session, account: LedgerAccount) -> str:
    """Return the code of the group an account sits in."""
    group = session.get(AccountGroup, account.account_group_id)
    assert group is not None
    return group.code


def _as_before_the_change(session: Session, firm_id: UUID) -> None:
    """Take a firm's books back to before the four accounts existed."""
    for name in _NEW:
        for row in _accounts(session, firm_id).get(name, []):
            session.delete(row)
    session.commit()


def _cash_under_current_assets(session: Session, firm_id: UUID) -> None:
    """Put Cash straight under Current Assets, as firms opened early have it."""
    current = session.scalar(
        select(AccountGroup).where(
            AccountGroup.firm_id == firm_id, AccountGroup.code == "CA"
        )
    )
    cash = session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.firm_id == firm_id, LedgerAccount.code == "1000"
        )
    )
    assert current is not None and cash is not None
    cash.account_group_id = current.id
    session.commit()


def _migration() -> ModuleType:
    """Load the migration module by path; its name starts with a digit."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261012_0355_ready_made_accounts.py"
    )
    spec = spec_from_file_location("ready_made_accounts_migration", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(engine: Engine) -> None:
    """Replay the migration over a SQLite store, twice.

    Twice, because a store partly built by ``create_all`` replays it. SQLite
    has no ``now()`` and does not bind a UUID, both of which the migration's
    PostgreSQL-shaped SQL relies on, so they are supplied here: a UUID as the
    string ``UUIDType`` stores.
    """
    sqlite3.register_adapter(UUID, str)
    with engine.connect() as connection:
        # One connection for the life of the engine (``StaticPool``).
        raw = connection.connection.driver_connection
        assert isinstance(raw, sqlite3.Connection)
        raw.create_function("now", 0, lambda: "2026-10-12 00:00:00")
    module = _migration()
    for _ in range(2):
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                module.upgrade()


def test_a_new_firm_opens_with_the_five_accounts() -> None:
    """Each is there once, of the right kind, in the right group, unmapped."""
    session = sessionmaker(bind=_engine(), expire_on_commit=False)()
    firm, _ = _opened_firm(session)

    accounts = _accounts(session, firm.id)
    for name, (code, kind, group) in _READY_MADE.items():
        assert len(accounts[name]) == 1, name
        row = accounts[name][0]
        assert (row.code, row.account_type) == (code, kind), name
        assert _group_code(session, row) == group, name
        assert row.is_profit_loss is (kind == "EXPENSE"), name
        assert row.is_balance_sheet is (kind != "EXPENSE"), name

    # A person chooses the four new ones; no document posts to them.
    mapped = set(
        session.scalars(
            select(FirmControlAccount.ledger_account_id).where(
                FirmControlAccount.firm_id == firm.id
            )
        )
    )
    for name in _NEW:
        assert accounts[name][0].id not in mapped, name


def test_petty_cash_is_money_and_is_read_by_the_cash_book() -> None:
    """It is offered wherever cash is paid from, and the cash book reads it."""
    session = sessionmaker(bind=_engine(), expire_on_commit=False)()
    firm, _ = _opened_firm(session)
    petty = _accounts(session, firm.id)["Petty Cash"][0]

    money = ContraVoucherService(session).money_accounts(firm.id)
    offered = {row.id: row.kind for row in money}
    assert offered[petty.id] == MoneyAccountKindEnum.CASH
    assert petty.id in BooksRegisterService(session).money_accounts(
        firm.id, ControlAccountPurpose.CASH
    )
    assert petty.id not in BooksRegisterService(session).money_accounts(
        firm.id, ControlAccountPurpose.BANK
    )


def test_opening_the_books_again_adds_only_what_is_missing() -> None:
    """The firm's own Fuel, its renamed account and its number 3200 all stay."""
    session = sessionmaker(bind=_engine(), expire_on_commit=False)()
    firm, actor_id = _opened_firm(session)
    _as_before_the_change(session, firm.id)
    _cash_under_current_assets(session, firm.id)
    groups = {
        row.code: row.id
        for row in session.scalars(
            select(AccountGroup).where(AccountGroup.firm_id == firm.id)
        )
    }
    # Its own Fuel under its own number; a loan holding 3200; and 6450 kept
    # for an expense it calls something else.
    session.add_all(
        [
            LedgerAccount(
                firm_id=firm.id,
                account_group_id=groups["EXP"],
                code="5900",
                name="FUEL",
                account_type="EXPENSE",
                is_profit_loss=True,
                is_balance_sheet=False,
            ),
            LedgerAccount(
                firm_id=firm.id,
                account_group_id=groups["CL"],
                code="3200",
                name="Loan from Partner",
                account_type="LIABILITY",
            ),
            LedgerAccount(
                firm_id=firm.id,
                account_group_id=groups["IEXP"],
                code="6450",
                name="Lorry Hire",
                account_type="EXPENSE",
                is_profit_loss=True,
                is_balance_sheet=False,
            ),
        ]
    )
    session.commit()

    created = seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    session.commit()

    # Petty Cash and Capital only: Fuel is the firm's own, and 6450 is its
    # Transport under the name it chose.
    assert created["accounts"] == 2
    assert created["groups"] == 0
    accounts = _accounts(session, firm.id)
    assert [row.code for row in accounts["FUEL"]] == ["5900"]
    assert "Fuel" not in accounts
    assert "Transport" not in accounts
    assert [row.code for row in accounts["Lorry Hire"]] == ["6450"]
    assert [row.code for row in accounts["Loan from Partner"]] == ["3200"]
    assert [row.code for row in accounts["Capital"]] == ["3201"]
    assert accounts["Capital"][0].account_type == "EQUITY"
    # Beside the firm's Cash, wherever that firm keeps it.
    assert _group_code(session, accounts["Petty Cash"][0]) == "CA"

    again = seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    assert again["accounts"] == 0


def test_the_migration_gives_an_existing_firm_what_a_new_firm_gets() -> None:
    """Replayed over books opened before the change, it matches the seed."""
    engine = _engine()
    with Session(engine, expire_on_commit=False) as session:
        firm, _ = _opened_firm(session)
        before = {
            row.id: (row.code, row.name, row.version)
            for rows in _accounts(session, firm.id).values()
            for row in rows
            if row.name not in _NEW
        }
        _as_before_the_change(session, firm.id)
        # A second firm whose books were never opened is left alone.
        unopened = Firm(
            name="Later Firm",
            code="LATER",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(unopened)
        session.commit()
        firm_id, unopened_id = firm.id, unopened.id

    _run_migration(engine)

    with Session(engine) as session:
        accounts = _accounts(session, firm_id)
        for name, (code, kind, group) in _READY_MADE.items():
            assert len(accounts[name]) == 1, name
            row = accounts[name][0]
            assert (row.code, row.account_type) == (code, kind), name
            assert _group_code(session, row) == group, name
            assert row.is_profit_loss is (kind == "EXPENSE"), name
            assert row.is_balance_sheet is (kind != "EXPENSE"), name
            assert row.is_active and row.version == 1, name
        after = {
            row.id: (row.code, row.name, row.version)
            for rows in accounts.values()
            for row in rows
            if row.name not in _NEW
        }
        assert after == before
        assert _accounts(session, unopened_id) == {}


def test_the_migration_keeps_what_the_firm_already_has() -> None:
    """Its own account of the name stays the only one; a taken number is passed."""
    engine = _engine()
    with Session(engine, expire_on_commit=False) as session:
        firm, _ = _opened_firm(session)
        _as_before_the_change(session, firm.id)
        _cash_under_current_assets(session, firm.id)
        groups = {
            row.code: row.id
            for row in session.scalars(
                select(AccountGroup).where(AccountGroup.firm_id == firm.id)
            )
        }
        session.add_all(
            [
                LedgerAccount(
                    firm_id=firm.id,
                    account_group_id=groups["IEXP"],
                    code="6999",
                    name="transport",
                    account_type="EXPENSE",
                    is_profit_loss=True,
                    is_balance_sheet=False,
                ),
                LedgerAccount(
                    firm_id=firm.id,
                    account_group_id=groups["CL"],
                    code="3200",
                    name="Loan from Partner",
                    account_type="LIABILITY",
                ),
            ]
        )
        session.commit()
        firm_id = firm.id

    _run_migration(engine)

    with Session(engine) as session:
        accounts = _accounts(session, firm_id)
        assert [row.code for row in accounts["transport"]] == ["6999"]
        assert "Transport" not in accounts
        assert [row.code for row in accounts["Loan from Partner"]] == ["3200"]
        assert [row.code for row in accounts["Capital"]] == ["3201"]
        assert [row.code for row in accounts["Fuel"]] == ["6460"]
        assert _group_code(session, accounts["Petty Cash"][0]) == "CA"
