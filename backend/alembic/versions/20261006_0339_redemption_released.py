"""A claim on an offer records the part that was given back undelivered.

``promotion_redemptions.released_benefit_amount``,
``released_free_quantity`` and ``released_at`` -- what an order closed short
never delivered of the discount and the free units it claimed (D-PRC-28).
``benefit_amount`` and ``free_quantity`` stay what the document claimed; an
offer's budgets, its reports and a principal's claim read the difference.

Both amounts default to zero, so every existing claim reads as it did: all of
it given. An order closed short before this revision keeps its whole claim --
nothing recorded how much of it was delivered when it closed.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0339
Revises: 20261006_0338
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0339"
down_revision: str | Sequence[str] | None = "20261006_0338"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLAIMS = "promotion_redemptions"
_AMOUNTS = ("released_benefit_amount", "released_free_quantity")
_WHEN = "released_at"


def _columns(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return a table's column names, or None where the store has no such table."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the columns where the store keeps claims on offers."""
    claims = _columns(sa.inspect(op.get_bind()), _CLAIMS)
    if claims is None:
        return
    for name in _AMOUNTS:
        if name not in claims:
            op.add_column(
                _CLAIMS,
                sa.Column(
                    name,
                    sa.Numeric(18, 4),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )
    if _WHEN not in claims:
        op.add_column(
            _CLAIMS, sa.Column(_WHEN, sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Drop the columns."""
    claims = _columns(sa.inspect(op.get_bind()), _CLAIMS)
    if claims is None:
        return
    for name in (_WHEN, *_AMOUNTS):
        if name in claims:
            op.drop_column(_CLAIMS, name)
