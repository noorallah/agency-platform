"""Cash discount for early payment and interest on overdue bills (SEL-14, A91).

* ``customers.cash_discount_days`` / ``cash_discount_percent``.
* ``credit_control_settings``: the firm's ``cash_discount_days`` /
  ``cash_discount_percent``, ``overdue_interest_rate`` (0) and
  ``interest_grace_days`` (0).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0262
Revises: 20261003_0261
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0262"
down_revision: str | Sequence[str] | None = "20261003_0261"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED: dict[str, tuple[sa.Column[object], ...]] = {
    "customers": (
        sa.Column("cash_discount_days", sa.Integer()),
        sa.Column("cash_discount_percent", sa.Numeric(9, 4)),
    ),
    "credit_control_settings": (
        sa.Column("cash_discount_days", sa.Integer()),
        sa.Column("cash_discount_percent", sa.Numeric(9, 4)),
        sa.Column(
            "overdue_interest_rate",
            sa.Numeric(7, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "interest_grace_days",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    ),
}


def upgrade() -> None:
    """Add each column where its table lacks it."""
    inspector = sa.inspect(op.get_bind())
    for table, columns in _ADDED.items():
        if not inspector.has_table(table):
            continue
        have = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in have:
                op.add_column(table, column.copy())


def downgrade() -> None:
    """Drop the columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table, columns in _ADDED.items():
        if not inspector.has_table(table):
            continue
        have = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name in have:
                op.drop_column(table, column.name)
