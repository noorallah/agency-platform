"""A branch's own GSTIN (STK-2, decision A127).

``branches.gstin``: the registration a branch in a state of its own supplies
under. Empty means the firm's GSTIN, which is every branch today.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0289
Revises: 20261003_0288
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0289"
down_revision: str | Sequence[str] | None = "20261003_0288"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column where a store has branches and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("branches"):
        return
    columns = {column["name"] for column in inspector.get_columns("branches")}
    if "gstin" not in columns:
        op.add_column("branches", sa.Column("gstin", sa.String(15), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("branches"):
        return
    columns = {column["name"] for column in inspector.get_columns("branches")}
    if "gstin" in columns:
        op.drop_column("branches", "gstin")
