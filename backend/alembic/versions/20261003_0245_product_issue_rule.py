"""Which batch a product leaves from (STK-11, decision A63).

`products.issue_rule`: FEFO (earliest expiry first), FIFO (first received
first) or PICK (a person chooses the batch on the line; dispatch never draws
silently). Null is FEFO, which every product followed before.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0245
Revises: 20261003_0244
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0245"
down_revision: str | Sequence[str] | None = "20261003_0244"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "products"
_COLUMN = "issue_rule"


def upgrade() -> None:
    """Add the rule, where the products table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(10), nullable=True))


def downgrade() -> None:
    """Drop the rule."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
