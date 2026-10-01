"""Keep the volume seeder's row builders honest (backlog 56 C, step 5).

``scripts/seed_volume_firm.py`` writes two years of trading straight into the
tables, bypassing every service, so nothing else in the suite would notice a
column it forgot, a table that was renamed, or a journal that stopped
balancing. This runs the same simulator at a tiny scale against SQLite -- a
handful of products, a few weeks -- and checks the consistency the seeder
promises: every journal balanced, the ledger balances equal to the journals,
stock rows equal to their movements, and customer balances equal to their
receivable transactions.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from scripts.seed_volume_firm import (
    SERIES_KEYS,
    FirmContext,
    Period,
    Scale,
    Sink,
    TaxSlab,
    TradeSimulator,
    fy_label,
    fy_start,
)

#: The purposes the trading posts to, with the account type each would have.
PURPOSES = {
    "CASH": "ASSET",
    "BANK": "ASSET",
    "ACCOUNTS_RECEIVABLE": "ASSET",
    "INVENTORY": "ASSET",
    "INPUT_TAX_CGST": "ASSET",
    "INPUT_TAX_SGST": "ASSET",
    "ACCOUNTS_PAYABLE": "LIABILITY",
    "OUTPUT_TAX": "LIABILITY",
    "GOODS_RECEIVED_NOT_INVOICED": "LIABILITY",
    "OPENING_BALANCE_EQUITY": "EQUITY",
    "SALES_REVENUE": "INCOME",
    "SALES_RETURNS": "INCOME",
    "COST_OF_GOODS_SOLD": "EXPENSE",
    "PURCHASE_PRICE_VARIANCE": "EXPENSE",
}

START = date(2025, 3, 1)
END = date(2025, 5, 31)


def _months(start: date, end: date) -> list[Period]:
    """Return one period per calendar month from ``start`` through ``end``."""
    periods = []
    current = date(start.year, start.month, 1)
    while current <= end:
        following = date(current.year + current.month // 12, current.month % 12 + 1, 1)
        periods.append(
            Period(uuid4(), current, date.fromordinal(following.toordinal() - 1))
        )
        current = following
    return periods


def _context() -> FirmContext:
    """Return a context made of fresh ids, shaped as ``read_context`` builds it."""
    accounts = {purpose: uuid4() for purpose in PURPOSES}
    slab = TaxSlab(Decimal("18"), uuid4(), "GST_18_LOCAL", uuid4(), uuid4())
    labels = {fy_label(START), fy_label(END)}
    return FirmContext(
        firm_id=uuid4(),
        actor_id=uuid4(),
        branch_id=uuid4(),
        warehouse_ids=[uuid4(), uuid4(), uuid4()],
        business_profile_id=None,
        accounts=accounts,
        account_types={accounts[p]: kind for p, kind in PURPOSES.items()},
        journal_type_id=uuid4(),
        voucher_type_id=uuid4(),
        periods=_months(START, END),
        slabs=[slab, TaxSlab(Decimal("5"), uuid4(), "GST_5_LOCAL", uuid4(), uuid4())],
        prefixes={
            key: {label: f"{key}-{label}-" for label in labels} for key in SERIES_KEYS
        },
        padding={key: 6 for key in SERIES_KEYS},
        document_types={key: uuid4() for key in SERIES_KEYS},
        uom_id=None,
        start=START,
        end=END,
    )


@pytest.fixture(scope="module")
def seeded() -> Iterator[tuple[Connection, TradeSimulator]]:
    """Run the simulator once, at a tiny scale, into an in-memory SQLite."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        sink = Sink(connection, batch_size=500)
        simulator = TradeSimulator(_context(), sink, Scale(0.004), rng=random.Random(7))
        simulator.RETURN_SHARE = 0.08
        simulator.CREDIT_NOTE_SHARE = 0.08
        simulator.run()
        simulator.finish(connection)
        yield connection, simulator
    engine.dispose()


def _table(name: str) -> object:
    """Return a table from the metadata."""
    return Base.metadata.tables[name]


def test_the_scale_never_drops_below_a_working_minimum() -> None:
    """A quick run still has enough of everything to trade."""
    tiny = Scale(0.0001)
    assert (tiny.products, tiny.customers, tiny.suppliers) == (20, 10, 3)
    full = Scale(1.0)
    assert (full.products, full.customers, full.suppliers) == (5_000, 2_000, 300)
    assert full.invoices_per_day == 150


def test_the_financial_year_starts_in_april() -> None:
    """Numbers and books follow the April year the firm is created with."""
    assert fy_start(date(2025, 3, 31)) == date(2024, 4, 1)
    assert fy_start(date(2025, 4, 1)) == date(2025, 4, 1)
    assert fy_label(date(2025, 4, 1)) == "2025-2026"


def test_the_whole_chain_was_written(
    seeded: tuple[Connection, TradeSimulator],
) -> None:
    """Every table the trading writes has rows, and the sink counted them."""
    connection, simulator = seeded
    for name in (
        "products",
        "batches",
        "customers",
        "vendors",
        "sales_orders",
        "delivery_note_lines",
        "sales_invoice_line_taxes",
        "sales_invoice_sources",
        "purchase_invoice_line_taxes",
        "goods_receipt_lines",
        "settlement_allocations",
        "sales_returns",
        "credit_notes",
        "document_lifecycle_events",
        "audit_logs",
        "gl_postings",
        "ledger_balances",
        "product_valuations",
        "opening_stock_lines",
    ):
        rows = connection.execute(
            select(func.count()).select_from(_table(name))  # type: ignore[arg-type]
        ).scalar()
        assert rows, f"{name} is empty"
        assert simulator.sink.counts[name] == rows, name
    invoices = connection.execute(
        select(func.count()).select_from(_table("sales_invoices"))  # type: ignore[arg-type]
    ).scalar()
    movements = connection.execute(
        select(_table("inventory_transactions").c.transaction_type)  # type: ignore[attr-defined]
    ).scalars()
    kinds = defaultdict(int)
    for kind in movements:
        kinds[kind] += 1
    # Every sold line writes RESERVE, UNRESERVE and DISPATCH, as the real flow.
    assert kinds["RESERVE"] == kinds["UNRESERVE"] == kinds["DISPATCH"] >= invoices


def test_every_journal_balances_and_the_ledger_matches_it(
    seeded: tuple[Connection, TradeSimulator],
) -> None:
    """The trial balance balances, and each account's closing is its journals."""
    connection, simulator = seeded
    lines = _table("journal_lines")
    by_entry = connection.execute(
        select(
            lines.c.journal_entry_id,  # type: ignore[attr-defined]
            func.sum(lines.c.debit_amount),  # type: ignore[attr-defined]
            func.sum(lines.c.credit_amount),  # type: ignore[attr-defined]
        ).group_by(
            lines.c.journal_entry_id
        )  # type: ignore[attr-defined]
    ).all()
    assert by_entry
    assert all(Decimal(debit) == Decimal(credit) for _, debit, credit in by_entry)

    balances = _table("ledger_balances")
    periods = {period.id: period for period in simulator.ctx.periods}
    latest: dict[UUID, tuple[date, Decimal]] = {}
    for account, period_id, closing in connection.execute(
        select(
            balances.c.ledger_account_id,  # type: ignore[attr-defined]
            balances.c.accounting_period_id,  # type: ignore[attr-defined]
            balances.c.closing_balance,  # type: ignore[attr-defined]
        )
    ):
        ends = periods[period_id].ends_on
        if account not in latest or latest[account][0] < ends:
            latest[account] = (ends, Decimal(closing))
    types = simulator.ctx.account_types
    debit_side = sum(
        (c for a, (_, c) in latest.items() if types[a] in {"ASSET", "EXPENSE"}),
        Decimal(0),
    )
    credit_side = sum(
        (c for a, (_, c) in latest.items() if types[a] not in {"ASSET", "EXPENSE"}),
        Decimal(0),
    )
    assert debit_side == credit_side


def test_stock_rows_equal_their_movements(
    seeded: tuple[Connection, TradeSimulator],
) -> None:
    """``inventories`` is the sum of its movements; the valuation, of those."""
    connection, _ = seeded
    stock = _table("inventories")
    movements = _table("inventory_transactions")
    summed = dict(
        connection.execute(
            select(
                movements.c.inventory_id,  # type: ignore[attr-defined]
                func.sum(movements.c.current_quantity_delta),  # type: ignore[attr-defined]
            ).group_by(
                movements.c.inventory_id
            )  # type: ignore[attr-defined]
        ).all()
    )
    rows = connection.execute(
        select(
            stock.c.id,  # type: ignore[attr-defined]
            stock.c.current_quantity,  # type: ignore[attr-defined]
            stock.c.reserved_quantity,  # type: ignore[attr-defined]
        )
    ).all()
    assert rows
    for inventory_id, current, reserved in rows:
        assert Decimal(current) == Decimal(summed.get(inventory_id, 0))
        assert Decimal(current) >= 0
        assert Decimal(reserved) == 0
    valuations = _table("product_valuations")
    on_hand = connection.execute(
        select(func.sum(valuations.c.quantity_on_hand))  # type: ignore[attr-defined]
    ).scalar()
    total = connection.execute(
        select(func.sum(stock.c.current_quantity))  # type: ignore[attr-defined]
    ).scalar()
    assert Decimal(on_hand) == Decimal(total)


def test_customer_balances_equal_their_receivable_trail(
    seeded: tuple[Connection, TradeSimulator],
) -> None:
    """A customer's balance is the sum of what moved it, and the ledger agrees."""
    connection, simulator = seeded
    trail = _table("customer_receivable_transactions")
    moved = {
        customer: (Decimal(outstanding), Decimal(advance))
        for customer, outstanding, advance in connection.execute(
            select(
                trail.c.customer_id,  # type: ignore[attr-defined]
                func.sum(trail.c.outstanding_delta),  # type: ignore[attr-defined]
                func.sum(trail.c.advance_delta),  # type: ignore[attr-defined]
            ).group_by(
                trail.c.customer_id
            )  # type: ignore[attr-defined]
        )
    }
    customers = _table("customers")
    outstanding_total = advance_total = Decimal(0)
    for customer, outstanding, advance in connection.execute(
        select(
            customers.c.id,  # type: ignore[attr-defined]
            customers.c.current_outstanding,  # type: ignore[attr-defined]
            customers.c.unapplied_advance_balance,  # type: ignore[attr-defined]
        )
    ):
        expected = moved.get(customer, (Decimal(0), Decimal(0)))
        assert (Decimal(outstanding), Decimal(advance)) == expected
        outstanding_total += Decimal(outstanding)
        advance_total += Decimal(advance)
    receivable = simulator.ctx.accounts["ACCOUNTS_RECEIVABLE"]
    ledger = sum(
        (
            debit - credit
            for (a, _), (debit, credit) in simulator.ledger.items()
            if a == receivable
        ),
        Decimal(0),
    )
    assert ledger == outstanding_total - advance_total


def test_document_numbers_are_unique_and_follow_the_series(
    seeded: tuple[Connection, TradeSimulator],
) -> None:
    """Numbers are issued once each, and the counters know how far they got."""
    connection, simulator = seeded
    invoices = _table("sales_invoices")
    numbers = (
        connection.execute(
            select(invoices.c.invoice_number)  # type: ignore[attr-defined]
        )
        .scalars()
        .all()
    )
    assert len(numbers) == len(set(numbers))
    assert all(number.startswith("SI-") for number in numbers)
    issued = sum(used for (key, _), used in simulator.counters.items() if key == "SI")
    assert issued == len(numbers)
