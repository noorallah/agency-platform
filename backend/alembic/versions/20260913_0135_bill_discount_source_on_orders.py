"""Record where a sales order's whole-order discount came from.

`bill_discount_amount` holds the amount applied whether somebody typed it or
a promotion set it, and nothing said which. The desktop order editor refilled
the box with a promotion's figure as though typed, so saving an order again
sent it back as a typed discount -- which outranks every promotion -- and
the offer stopped applying, its claim went, and the discount stayed even
after the order shrank below the offer's threshold (manual plan item 10.7,
2026-09-13).

``bill_discount_source`` is nullable and additive: ``typed``, ``promotion``
or ``none``. Existing orders stay NULL, which the editor treats as typed, as
it always did. The table is firm-owned, so run this through
``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0135"
down_revision: str | Sequence[str] | None = "20260913_0134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_orders"
_COLUMN = "bill_discount_source"


def upgrade() -> None:
    """Add the nullable column where the table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return
    if any(column["name"] == _COLUMN for column in inspector.get_columns(_TABLE)):
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Drop the column where it exists."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and any(
        column["name"] == _COLUMN for column in inspector.get_columns(_TABLE)
    ):
        op.drop_column(_TABLE, _COLUMN)
