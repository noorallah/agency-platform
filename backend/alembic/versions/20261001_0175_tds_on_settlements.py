"""Tax deducted at source on payments, receipts and expenses (backlog 53.1).

``settlements`` and ``expenses`` each gain ``tds_amount`` (default 0) and
``tds_section``; ``expenses`` also gains ``payee_pan``, which the return names
the deductee by. Existing rows deducted nothing, which is what the default
says, so nothing is backfilled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261001_0175
Revises: 20261001_0174
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0175"
down_revision: str | Sequence[str] | None = "20261001_0174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES: tuple[str, ...] = ("settlements", "expenses")


def _columns(table: str) -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns this revision adds to ``table``."""
    columns: list[sa.Column] = [  # type: ignore[type-arg]
        sa.Column(
            "tds_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("tds_section", sa.String(10), nullable=True),
    ]
    if table == "expenses":
        columns.append(sa.Column("payee_pan", sa.String(10), nullable=True))
    return columns


def upgrade() -> None:
    """Add the TDS columns where the table exists and they do not."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for column in _columns(table):
            if column.name not in present:
                op.add_column(table, column)


def downgrade() -> None:
    """Drop the TDS columns."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for column in reversed(_columns(table)):
            if column.name in present:
                op.drop_column(table, column.name)
