"""A commission rule can have a floor, and pay more for meeting a target.

Two arrangements every distribution firm runs and neither of which could be
expressed.

`minimum_amount` is a floor on the **arrangement**: nothing is earned under
the rule until the subtotal reaches it. Deliberately not a zero-percent bottom
slab, which is a different deal -- a ladder pays from the first rupee once it
is climbed, while "no commission below ten lakh a quarter" pays nothing at all
until the quarter is made.

`bonus_percentage` is an extra percentage on the same subtotal, paid only when
the salesman's targets over the period were met, taken together. A field on
the rule rather than a second rule, because two live rules over one person's
days are refused -- the overlap guard exists so a payout is never left to
whichever row a query returned first, and weakening it to allow a bonus rule
would reopen exactly that.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0117
Revises: 20260903_0116
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0117"
down_revision: str | Sequence[str] | None = "20260903_0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_rules"


def _columns(inspector: sa.Inspector) -> set[str]:
    """Return the column names the rule table already has."""
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the floor and the target bonus."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_invoices") or not inspector.has_table(_TABLE):
        return
    existing = _columns(inspector)
    if "minimum_amount" not in existing:
        op.add_column(
            _TABLE, sa.Column("minimum_amount", sa.Numeric(18, 2), nullable=True)
        )
    if "bonus_percentage" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "bonus_percentage",
                sa.Numeric(9, 4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Drop the floor and the target bonus."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = _columns(inspector)
    for column in ("bonus_percentage", "minimum_amount"):
        if column in existing:
            op.drop_column(_TABLE, column)
