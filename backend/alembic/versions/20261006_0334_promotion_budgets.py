"""A scheme has a budget, in money and in free units.

``promotions.max_benefit_amount`` and ``promotions.max_free_quantity`` -- the
most an offer may give away over its life, as discount and as free goods.
Null on every existing offer, which is "no budget": what each had before.

``promotion_redemptions.free_quantity`` -- the free units a claim gave, so
the second budget can be counted from the ledger as the first is counted
from ``benefit_amount``. It defaults to zero. Claims made before this
revision keep zero: what they gave free was never recorded on the claim, so
a free-quantity budget set on an offer already running counts from here on.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0334
Revises: 20261005_0333
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0334"
down_revision: str | Sequence[str] | None = "20261005_0333"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OFFERS = "promotions"
_BUDGETS = ("max_benefit_amount", "max_free_quantity")
_CLAIMS = "promotion_redemptions"
_GIVEN = "free_quantity"


def _columns(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return a table's column names, or None where the store has no such table."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the columns where the store keeps promotions."""
    inspector = sa.inspect(op.get_bind())
    offers = _columns(inspector, _OFFERS)
    if offers is not None:
        for name in _BUDGETS:
            if name not in offers:
                op.add_column(
                    _OFFERS, sa.Column(name, sa.Numeric(18, 4), nullable=True)
                )
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _GIVEN not in claims:
        op.add_column(
            _CLAIMS,
            sa.Column(
                _GIVEN, sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")
            ),
        )


def downgrade() -> None:
    """Drop the columns."""
    inspector = sa.inspect(op.get_bind())
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _GIVEN in claims:
        op.drop_column(_CLAIMS, _GIVEN)
    offers = _columns(inspector, _OFFERS)
    if offers is not None:
        for name in _BUDGETS:
            if name in offers:
                op.drop_column(_OFFERS, name)
