"""Let a settlement be a refund to a customer.

`settlements` allowed a customer against a RECEIPT and a vendor against a
PAYMENT, and nothing else. A refund is money out like a payment and about a
customer like a receipt, so it was neither and could not be recorded -- which
left `POST /customers/{id}/receivables/transactions` accepting a REFUND that
moved the customer's advance and wrote no journal.

The check constraint is widened rather than dropped: a receipt or a refund
carries a customer and no vendor, a payment carries a vendor and no customer.
Getting that wrong is how a firm ends up with a settlement against nobody.

`settlements` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0082"
down_revision: str | Sequence[str] | None = "20260814_0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "settlements"
_CONSTRAINT = "CK_settlements_party_matches_direction"

_OLD = (
    "(direction = 'RECEIPT' AND customer_id IS NOT NULL AND vendor_id IS NULL) "
    "OR (direction = 'PAYMENT' AND vendor_id IS NOT NULL "
    "AND customer_id IS NULL)"
)
_NEW = (
    "(direction IN ('RECEIPT', 'REFUND') AND customer_id IS NOT NULL "
    "AND vendor_id IS NULL) OR (direction = 'PAYMENT' AND vendor_id IS NOT NULL "
    "AND customer_id IS NULL)"
)


def _has_table() -> bool:
    """Return whether the settlements table is in this store, asked for now."""
    return sa.inspect(op.get_bind()).has_table(_TABLE)


def _swap(condition: str) -> None:
    """Replace the party constraint with one carrying this condition."""
    if not _has_table():
        return
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, condition)


def upgrade() -> None:
    """Widen the party constraint to allow a refund against a customer."""
    _swap(_NEW)


def downgrade() -> None:
    """Narrow it again, leaving any refund rows in violation to be dealt with."""
    _swap(_OLD)
