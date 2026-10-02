"""The e-way bill on a goods receipt (backlog 78 row 6).

``goods_receipts`` gains ``eway_bill_number`` and ``eway_bill_date``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where the table exists and lacks it.

Revision ID: 20261002_0233
Revises: 20261002_0232
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0233"
down_revision: str | Sequence[str] | None = "20261002_0232"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> tuple[sa.Column, ...]:  # type: ignore[type-arg]
    """Return the columns this revision adds, fresh each call."""
    return (
        sa.Column("eway_bill_number", sa.String(length=12)),
        sa.Column("eway_bill_date", sa.Date()),
    )


def upgrade() -> None:
    """Add each column where the receipts are held and lack it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("goods_receipts"):
        return
    present = {column["name"] for column in inspector.get_columns("goods_receipts")}
    for column in _columns():
        if column.name not in present:
            op.add_column("goods_receipts", column)


def downgrade() -> None:
    """Drop each column where it was added."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("goods_receipts"):
        return
    present = {column["name"] for column in inspector.get_columns("goods_receipts")}
    for column in _columns():
        if column.name in present:
            op.drop_column("goods_receipts", column.name)
