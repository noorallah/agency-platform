"""A commission slab pays a fixed amount or a percentage (backlog 110).

``commission_rule_slabs.fixed_amount``: the sum a rung pays once the subtotal
reaches it. NULL is a percentage rung, which is every rung already stored, so
no existing ladder changes what it pays and there is nothing to backfill.

``CK_commission_rule_slabs_one_payment`` is the backstop for "never both": a
rung with a fixed amount holds a percentage of zero.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column and
the constraint are each added only where the store holds the table and lacks
them, because a firm store is partly built by ``Base.metadata.create_all`` and
can already have both.

Revision ID: 20261013_0356
Revises: 20261012_0355
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0356"
down_revision: str | Sequence[str] | None = "20261012_0355"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_rule_slabs"
_COLUMN = "fixed_amount"
_CHECK = "CK_commission_rule_slabs_one_payment"


def _columns(inspector: sa.Inspector) -> set[str]:
    """Return the column names the table already has."""
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def _checks(inspector: sa.Inspector) -> set[str | None]:
    """Return the names of the check constraints the table already has."""
    return {check["name"] for check in inspector.get_check_constraints(_TABLE)}


def upgrade() -> None:
    """Add the column and its constraint where a store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in _columns(inspector):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Numeric(18, 2), nullable=True))
    if _CHECK not in _checks(inspector):
        op.create_check_constraint(
            _CHECK,
            _TABLE,
            "fixed_amount IS NULL OR (fixed_amount >= 0 AND percentage = 0)",
        )


def downgrade() -> None:
    """Drop the constraint and the column where a store has them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _CHECK in _checks(inspector):
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    if _COLUMN in _columns(inspector):
        op.drop_column(_TABLE, _COLUMN)
