"""Re-chain every stored ledger balance from the movements it already holds.

A period's opening was copied from the previous closing once, when an
account was first posted to in that period, and never moved again -- so a
line dated into an earlier period afterwards left every later opening where
the earlier period used to close. WHOLE01's September trial balance read
612,368.97 against 671,088.58 and its balance sheet was out by the same
58,719.61, with every posting correct and 42 openings wrong (manual plan item
13.2, 2026-09-14). The journal engine now carries a back-dated line forward;
this puts right the balances written before it did.

Each account's rows are walked in period order: the first opens at nothing,
every later one opens at the closing before it, and each closes at its opening
plus its own period movement on the account's normal side. The period debit
and credit are left alone -- they already agree with ``gl_postings`` -- so
the result is determined by them and a replay changes nothing. Only rows that
differ are written. Firm-owned, so run through ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa

from alembic import op

revision: str = "20260914_0136"
down_revision: str | Sequence[str] | None = "20260913_0135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEBIT_SIDE = {"ASSET", "EXPENSE"}
_CENT = Decimal("0.01")


def upgrade() -> None:
    """Recompute openings and closings where the tables exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not all(
        inspector.has_table(name)
        for name in ("ledger_balances", "accounting_periods", "ledger_accounts")
    ):
        # The platform schema holds no firm-owned tables once pruned.
        return
    rows = bind.execute(
        sa.text(
            "SELECT b.id, b.ledger_account_id, a.account_type, b.opening_balance,"
            " b.period_debit, b.period_credit, b.closing_balance"
            " FROM ledger_balances b"
            " JOIN accounting_periods p ON p.id = b.accounting_period_id"
            " JOIN ledger_accounts a ON a.id = b.ledger_account_id"
            " ORDER BY b.firm_id, b.ledger_account_id, p.ends_on"
        )
    ).all()
    carried: dict[object, Decimal] = {}
    for row_id, account_id, account_type, opening, debit, credit, closing in rows:
        new_opening = carried.get(account_id, Decimal("0"))
        movement = Decimal(debit or 0) - Decimal(credit or 0)
        if account_type not in _DEBIT_SIDE:
            movement = -movement
        new_closing = (new_opening + movement).quantize(_CENT)
        new_opening = new_opening.quantize(_CENT)
        carried[account_id] = new_closing
        if Decimal(opening) == new_opening and Decimal(closing) == new_closing:
            continue
        bind.execute(
            sa.text(
                "UPDATE ledger_balances SET opening_balance = :opening,"
                " closing_balance = :closing WHERE id = :id"
            ),
            {"opening": new_opening, "closing": new_closing, "id": row_id},
        )


def downgrade() -> None:
    """Leave the balances as they are.

    The earlier figures were wrong, and nothing recorded which of them were;
    restoring them would be writing the defect back.
    """
