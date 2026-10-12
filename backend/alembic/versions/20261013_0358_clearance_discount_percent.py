"""The clearance discount a firm allows at collection (backlog 115).

``party_adjustment_settings.clearance_discount_percent``: the largest share of
the bills a receipt clears that may be waived as a discount beyond the
customer's terms. Nullable with no default -- blank is "no ceiling", which is
how every firm already stored behaved, so there is nothing to backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column and
its check are added only where the store holds the table and lacks them,
because a firm store is partly built by ``Base.metadata.create_all`` and can
already have both.

Revision ID: 20261013_0358
Revises: 20261013_0357
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0358"
down_revision: str | Sequence[str] | None = "20261013_0357"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "party_adjustment_settings"
_COLUMN = "clearance_discount_percent"
_CHECK = "CK_party_adjustment_settings_clearance"


def _has_column(inspector: sa.Inspector) -> bool:
    """Say whether the store's table already has the column."""
    return _COLUMN in {item["name"] for item in inspector.get_columns(_TABLE)}


def _has_check(inspector: sa.Inspector) -> bool:
    """Say whether the store's table already has the check."""
    return _CHECK in {item["name"] for item in inspector.get_check_constraints(_TABLE)}


def upgrade() -> None:
    """Add the column and its check where a store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if not _has_column(inspector):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Numeric(5, 2), nullable=True))
    if not _has_check(inspector):
        op.create_check_constraint(
            _CHECK,
            _TABLE,
            f"{_COLUMN} IS NULL OR ({_COLUMN} >= 0 AND {_COLUMN} <= 100)",
        )


def downgrade() -> None:
    """Drop the check and the column where a store has them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _has_check(inspector):
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    if _has_column(inspector):
        op.drop_column(_TABLE, _COLUMN)
