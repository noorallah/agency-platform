"""A payout remembers who approved it and who paid it (D-TER-4).

``approve`` and ``pay`` looked at the status and at nothing else, and the row
kept no approver or payer, so one person could accrue a payout, adjust it,
approve it and pay it -- their own included -- and only the audit trail could
say so. The service now refuses the payee, refuses the accruer at approval and
refuses the approver at payment, and the row carries the three signatures so
the record and the trail agree.

Three nullable columns on ``commission_payouts``:

- ``approved_by`` and ``approved_at`` -- set at approval, never cleared.
- ``paid_by`` -- set at payment.

No foreign keys: ``users`` lives only in the platform schema and this table is
in every firm store. Existing rows stay NULL, which is the truth -- nobody was
recorded -- and the payment check treats NULL as "no approver on record",
which refuses nobody it should not.

Idempotent: each column is added only where the table exists (the platform
schema holds no firm data once pruned) and the column is missing, because firm
stores are partly built by ``create_all``. Firm-owned, so run it through
``scripts/migrate_all_stores.py``.

Revision ID: 20260920_0151
Revises: 20260920_0150
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260920_0151"
down_revision: str | Sequence[str] | None = "20260920_0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_payouts"


def _columns() -> list[sa.Column]:
    """Return the three signature columns, all nullable."""
    return [
        sa.Column("approved_by", UUIDType(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by", UUIDType(), nullable=True),
    ]


def upgrade() -> None:
    """Add whichever of the three columns a firm store lacks."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name not in existing:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    """Drop the three columns, forgetting who signed."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name in existing:
            op.drop_column(_TABLE, column.name)
