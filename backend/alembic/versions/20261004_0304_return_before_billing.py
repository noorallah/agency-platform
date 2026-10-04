"""A return before billing reverses the accrual (D-BUY-26).

``purchase_return_lines.unbilled_quantity`` -- the part of a line taken off
what its goods receipt line still had to bill -- and ``grni_amount``, what
that part took off goods received not invoiced. Both default to zero, which is
what every line completed before this revision posted: the whole of it as a
debit note.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261004_0304
Revises: 20261004_0303
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_0304"
down_revision: str | Sequence[str] | None = "20261004_0303"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_return_lines"
_COLUMNS = ("unbilled_quantity", "grni_amount")


def upgrade() -> None:
    """Add the two columns where the store keeps purchase returns."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name in columns:
            continue
        op.add_column(
            _TABLE,
            sa.Column(
                name,
                sa.Numeric(18, 4),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    """Drop the two columns."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name in columns:
            op.drop_column(_TABLE, name)
