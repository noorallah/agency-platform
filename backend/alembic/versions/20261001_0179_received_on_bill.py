"""Money taken at the counter, on the bill itself (backlog 64 row 5).

``sales_invoices`` gains ``received_now_amount`` (0 for every bill today, so
nothing existing changes), ``received_now_method``, ``received_now_reference``
and ``received_now_settlement_id`` -- the receipt approval recorded.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261001_0179
Revises: 20261001_0178
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0179"
down_revision: str | Sequence[str] | None = "20261001_0178"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoices"


def _columns() -> list[sa.Column[object]]:
    """Return the columns this revision adds."""
    return [
        sa.Column(
            "received_now_amount",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("received_now_method", sa.String(10), nullable=True),
        sa.Column("received_now_reference", sa.String(120), nullable=True),
        sa.Column("received_now_settlement_id", UUIDType(), nullable=True),
    ]


def upgrade() -> None:
    """Add each column where the table exists and the column does not."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name not in present:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """Drop the columns."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in reversed(_columns()):
        if column.name in present:
            op.drop_column(_TABLE, column.name)
