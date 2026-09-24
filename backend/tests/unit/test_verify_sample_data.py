"""`verify_sample_data.py` compares each firm with its own ledger (D-FIN-16).

Its stock, receivable and control-account sums carried no ``firm_id``, so in
the shared store one firm's difference was added to another's and the two
could cancel -- MEDI01 out by +100 and FOOD01 by -100 read as a clean store.

The checks are plain SQL over a connection, so they are driven here on a
SQLite database holding only the columns they read.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, create_engine, text

from scripts.verify_sample_data import (
    _customers_against_the_ledger,
    _loyalty_against_the_ledger,
    _payables_moved_by_documents,
    _Result,
    _stock_against_the_ledger,
    _tcs_against_the_ledger,
)

_TABLES = (
    "CREATE TABLE firm_control_accounts (firm_id TEXT, ledger_account_id TEXT, "
    "purpose TEXT, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE gl_postings (firm_id TEXT, ledger_account_id TEXT, "
    "journal_entry_id TEXT, debit_amount NUMERIC DEFAULT 0, "
    "credit_amount NUMERIC DEFAULT 0, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE journal_entries (id TEXT, source_module TEXT, source_id TEXT, "
    "reversal_of_id TEXT, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE product_valuations (firm_id TEXT, total_value NUMERIC, "
    "is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE customers (firm_id TEXT, current_outstanding NUMERIC, "
    "unapplied_advance_balance NUMERIC DEFAULT 0, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE tcs_collections (firm_id TEXT, tcs_amount NUMERIC, "
    "status TEXT, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE loyalty_entries (firm_id TEXT, points NUMERIC, amount NUMERIC, "
    "is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE inventory_transactions (id TEXT, firm_id TEXT, "
    "transaction_type TEXT, reference_number TEXT, is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE stock_ledger_entries (transaction_id TEXT, total_cost NUMERIC, "
    "is_deleted BOOLEAN DEFAULT 0)",
    "CREATE TABLE goods_receipts (id TEXT, grn_number TEXT)",
)


@pytest.fixture
def connection() -> Iterator[Connection]:
    """Yield a connection to a store holding two firms, MEDI and FOOD."""
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        for statement in _TABLES:
            conn.execute(text(statement))
        yield conn
    engine.dispose()


def _map(conn: Connection, firm: str, purpose: str, account: str) -> None:
    """Map one purpose of one firm to an account."""
    conn.execute(
        text(
            "INSERT INTO firm_control_accounts (firm_id, ledger_account_id, purpose) "
            "VALUES (:firm, :account, :purpose)"
        ),
        {"firm": firm, "account": account, "purpose": purpose},
    )


def _post(
    conn: Connection,
    firm: str,
    account: str,
    *,
    debit: str = "0",
    credit: str = "0",
    journal: str = "j",
    source: str | None = "doc",
) -> None:
    """Post one line and the journal it belongs to."""
    conn.execute(
        text("INSERT INTO journal_entries (id, source_module) VALUES (:id, :src)"),
        {"id": journal, "src": source},
    )
    conn.execute(
        text(
            "INSERT INTO gl_postings (firm_id, ledger_account_id, journal_entry_id, "
            "debit_amount, credit_amount) VALUES (:f, :a, :j, :d, :c)"
        ),
        {"f": firm, "a": account, "j": journal, "d": debit, "c": credit},
    )


def _result() -> _Result:
    """Return an empty result that names the two firms."""
    return _Result(label="shared", firm_names={"medi": "MEDI01", "food": "FOOD01"})


def test_two_firms_differences_no_longer_cancel(connection: Connection) -> None:
    """MEDI's stock is 100 over its ledger and FOOD's 100 under: both fail."""
    for firm in ("medi", "food"):
        _map(connection, firm, "INVENTORY", f"{firm}-1200")
        _map(connection, firm, "ACCOUNTS_RECEIVABLE", f"{firm}-1100")
    _post(connection, "medi", "medi-1200", debit="500", journal="j1")
    _post(connection, "food", "food-1200", debit="500", journal="j2")
    connection.execute(
        text(
            "INSERT INTO product_valuations (firm_id, total_value) "
            "VALUES ('medi', 600), ('food', 400)"
        )
    )
    _post(connection, "medi", "medi-1100", debit="250", journal="j3")
    _post(connection, "food", "food-1100", debit="250", journal="j4")
    connection.execute(
        text(
            "INSERT INTO customers (firm_id, current_outstanding) "
            "VALUES ('medi', 300), ('food', 200)"
        )
    )
    result = _result()

    _stock_against_the_ledger(connection, result)
    _customers_against_the_ledger(connection, result)

    assert [failure.split(":")[0] for failure in result.failures] == [
        "FOOD01",
        "MEDI01",
        "FOOD01",
        "MEDI01",
    ]


def test_tcs_loyalty_and_payables_are_checked(connection: Connection) -> None:
    """The row's second half: none of the four was checked at all."""
    _map(connection, "medi", "TCS_PAYABLE", "medi-2400")
    _map(connection, "medi", "LOYALTY_PAYABLE", "medi-2600")
    _map(connection, "medi", "ACCOUNTS_PAYABLE", "medi-2000")
    # 12 of TCS collected, 10 posted by the collections; a hand remittance
    # of 5 is meant to reduce the account and is not counted.
    connection.execute(
        text(
            "INSERT INTO tcs_collections (firm_id, tcs_amount, status) VALUES "
            "('medi', 12, 'COLLECTED'), ('medi', 3, 'REVERSED')"
        )
    )
    _post(connection, "medi", "medi-2400", credit="10", journal="t1", source="tcs")
    _post(connection, "medi", "medi-2400", debit="5", journal="t2", source=None)
    # 80 earned, 30 spent: 50 held, against 40 owed in the ledger.
    connection.execute(
        text(
            "INSERT INTO loyalty_entries (firm_id, points, amount) VALUES "
            "('medi', 80, 80), ('medi', -30, 30)"
        )
    )
    _post(connection, "medi", "medi-2600", credit="40", journal="l1")
    # A hand journal on payables.
    _post(connection, "medi", "medi-2000", credit="7", journal="h1", source=None)
    result = _result()

    _tcs_against_the_ledger(connection, result)
    _loyalty_against_the_ledger(connection, result)
    _payables_moved_by_documents(connection, result)

    assert any("TCS collected 12" in f and "out by 2" in f for f in result.failures)
    assert any(
        "points held are worth 50" in f and "out by 10" in f for f in result.failures
    )
    assert any("1 hand journal(s) moved accounts payable" in f for f in result.failures)
    assert result.checked == 3
    assert all(f.startswith("MEDI01:") for f in result.failures)
