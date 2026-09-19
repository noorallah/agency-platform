"""Let a quotation show the offers on the bill and on delivery (D-SELL-32).

A quotation asked the promotion engine for line discounts only, so an offer
on the whole bill, a free gift and free shipping reached the order and never
the quotation, which read higher than the order it became. Pricing it the
order's way needs two facts the table could not hold:

``bill_discount_source`` -- ``typed``, ``promotion`` or ``none``, nullable and
additive, as ``20260913_0135`` gave the sales order. The conversion hands the
order only a typed bill discount, and the desktop refills only a typed one.
Existing quotations stay NULL, which both read as typed: before this, a
quotation's bill discount could only have been typed.

``freight_waived_amount`` -- what a free-shipping offer took off the delivery
charge asked for, NOT NULL with a server default of zero so every existing
row reads as "nothing waived", which is true. The conversion hands the order
the charge that was asked, so the order decides afresh whether an offer
still waives it.

Idempotent: each column is added only where the table exists and lacks it,
because firm stores are partly built by ``create_all``. The table is
firm-owned, so run this through ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0140"
down_revision: str | Sequence[str] | None = "20260919_0139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_quotations"


def _columns() -> set[str] | None:
    """Return the table's column names, or None where it does not exist."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return None
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add both columns where the table exists and lacks them."""
    existing = _columns()
    if existing is None:
        return
    if "bill_discount_source" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("bill_discount_source", sa.String(length=20), nullable=True),
        )
    if "freight_waived_amount" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "freight_waived_amount",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Drop both columns where they exist."""
    existing = _columns()
    if existing is None:
        return
    for column in ("freight_waived_amount", "bill_discount_source"):
        if column in existing:
            op.drop_column(_TABLE, column)
