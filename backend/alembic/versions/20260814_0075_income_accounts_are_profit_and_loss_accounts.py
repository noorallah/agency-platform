"""Put income and expense accounts on the statement they belong to.

``ledger_accounts.is_balance_sheet`` and ``is_profit_loss`` were plain schema
defaults of ``True`` / ``False``, and nothing set them. Every account the
chart-of-accounts seeder built therefore claimed to be a balance sheet account
and no part of the profit and loss -- Sales, Purchases and Cost of Goods Sold
included. The account detail panel showed that to the user as fact.

The service now derives both from the account type when the caller does not
give them. This brings existing rows into line.

Only rows still at those defaults are touched, and only where the account type
decides the answer on its own: ``INCOME`` and ``EXPENSE`` accounts. An account
someone has already set deliberately -- a memo account put on the profit and
loss, an income account taken off it -- is left exactly as it is, because a
backfill that overwrites a decision is worse than the gap it closes.

The profit and loss report itself reads ``account_type`` rather than these
flags, so nothing depends on this running. It stops the screen contradicting
the report.

``ledger_accounts`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0075"
down_revision: str | Sequence[str] | None = "20260814_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "ledger_accounts"


def upgrade() -> None:
    """Flip income and expense accounts still carrying the old defaults."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        # Firm stores are partly built by ``Base.metadata.create_all`` from the
        # sample-data scripts, and a store without finance has nothing to fix.
        return
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_profit_loss = true, is_balance_sheet = false "
            "WHERE account_type IN ('INCOME', 'EXPENSE') "
            "AND is_profit_loss = false AND is_balance_sheet = true"
        )
    )


def downgrade() -> None:
    """Return income and expense accounts to the old defaults."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_profit_loss = false, is_balance_sheet = true "
            "WHERE account_type IN ('INCOME', 'EXPENSE') "
            "AND is_profit_loss = true AND is_balance_sheet = false"
        )
    )
