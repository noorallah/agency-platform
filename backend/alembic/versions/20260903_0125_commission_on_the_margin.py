"""Commission on what a sale made, not on what it was worth.

The last item of the incentives spec, and it was blocked on one thing:
`sales_invoice_lines` carried no cost, so there was nothing to take off the
sale price. The cost was recoverable all along -- `stock_ledger_entries` records
the moving average that actually left the warehouse on every dispatch -- but
recovering it at report time would answer about today's average rather than the
day's, and a payout approved in March would then disagree with the report beside
it. So it is **snapshotted onto the line** when the bill is raised, which is the
same reason a payout is snapshotted at accrual.

`sales_invoice_lines.cost_amount` is **nullable, and NULL is not zero.** An
invoice raised straight off a sales order has no dispatch behind it, so nothing
moved and nothing was costed; zero would say the goods were free, and a margin
rule reading one as the other pays commission on the whole sale price.

`commission_rules.measure` is VALUE or MARGIN, defaulted to VALUE so no existing
rule changes what it pays. MARGIN is a different arrangement rather than a
different rate: a firm selling at a thin markup pays far less on the same
turnover, which is the point of it.

Existing invoice lines keep a NULL cost. They are not backfilled: the moving
average has moved since, and a figure invented now would be a number nobody can
defend against the ledger it claims to come from.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0125
Revises: 20260903_0124
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0125"
down_revision: str | Sequence[str] | None = "20260903_0124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the cost snapshot and the measure a rule is paid on."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("sales_invoice_lines") and "cost_amount" not in {
        column["name"] for column in inspector.get_columns("sales_invoice_lines")
    }:
        # Nullable on purpose: NULL means nothing recorded what these goods
        # cost, which is not the same as their having been free.
        op.add_column(
            "sales_invoice_lines",
            sa.Column("cost_amount", sa.Numeric(18, 4), nullable=True),
        )
    if inspector.has_table("commission_rules") and "measure" not in {
        column["name"] for column in inspector.get_columns("commission_rules")
    }:
        op.add_column(
            "commission_rules",
            sa.Column(
                "measure",
                sa.String(length=20),
                nullable=False,
                server_default="VALUE",
            ),
        )


def downgrade() -> None:
    """Drop both, losing what every sale cost and every margin rule measured."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("commission_rules") and "measure" in {
        column["name"] for column in inspector.get_columns("commission_rules")
    }:
        op.drop_column("commission_rules", "measure")
    if inspector.has_table("sales_invoice_lines") and "cost_amount" in {
        column["name"] for column in inspector.get_columns("sales_invoice_lines")
    }:
        op.drop_column("sales_invoice_lines", "cost_amount")
