"""A sales return before billing credits nothing (D-SELL-55).

``sales_return_lines.unbilled_quantity`` -- the part of a line that came back
against a delivery note before any bill charged for it. That part moves stock
and cost only and lowers what the note may still be billed for; the rest is a
credit note. It defaults to zero, which is what every line completed before
this revision posted: the whole of it as a credit. The selling twin of
``20261004_0304``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261005_0331
Revises: 20261005_0330
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0331"
down_revision: str | Sequence[str] | None = "20261005_0330"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_return_lines"
_COLUMN = "unbilled_quantity"


def upgrade() -> None:
    """Add the column where the store keeps sales returns."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN, sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
