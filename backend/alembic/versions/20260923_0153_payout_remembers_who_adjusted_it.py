"""A payout remembers who adjusted it (D-TER-20).

#580 gave a payout three signatures -- accrued, approved, paid -- and refused
the payee and the accruer at approval and the approver at payment. The
adjustment had none: anyone holding COMMISSION_MANAGE could write any
``adjustment_amount``, the payee included, and then approve the number they
had written. ``adjusted_by`` is the fourth signature; the service refuses the
payee at adjustment and the adjuster at approval, and caps a positive
adjustment at what the period earned.

No foreign key: ``users`` lives only in the platform schema and this table is
in every firm store. Existing rows stay NULL -- nobody was recorded.

Idempotent: added only where the table exists and the column is missing,
because firm stores are partly built by ``create_all``. Firm-owned, so run it
through ``scripts/migrate_all_stores.py``.

Revision ID: 20260923_0153
Revises: 20260920_0151
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260923_0153"
down_revision: str | Sequence[str] | None = "20260920_0151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_payouts"
_COLUMN = "adjusted_by"


def upgrade() -> None:
    """Add the column where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))


def downgrade() -> None:
    """Drop the column, forgetting who adjusted."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
