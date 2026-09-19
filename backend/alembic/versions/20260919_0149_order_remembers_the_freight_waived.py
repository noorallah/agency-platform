"""Let a sales order remember the delivery charge an offer waived (D-SELL-35).

``sales_orders.freight_amount`` holds what is **charged** -- what was left
after a free-shipping offer took its share -- and nothing held what the offer
took. So an editor reopening the order could only send the post-waiver figure
back, and a save priced the order on that: the charge the customer was
originally asked for was lost, and if the order no longer qualified for the
offer it could never come back. The quotation had the same defect and the same
fix (D-SELL-34, ``20260919_0140``).

``freight_waived_amount`` is NOT NULL with a server default of zero, so every
existing row reads as "nothing waived", which is true of what they charged;
the two together are what the customer was asked.

Idempotent: added only where the table exists and lacks it, because firm
stores are partly built by ``create_all``. The table is firm-owned, so run
this through ``scripts/migrate_all_stores.py``.

Revision ID: 20260919_0149
Revises: 20260919_0148
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0149"
down_revision: str | Sequence[str] | None = "20260919_0148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_orders"
_COLUMN = "freight_waived_amount"


def _columns() -> set[str] | None:
    """Return the table's column names, or None where it does not exist."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return None
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the column where the table exists and lacks it."""
    existing = _columns()
    if existing is None or _COLUMN in existing:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Numeric(18, 4), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Drop the column where it exists."""
    existing = _columns()
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
