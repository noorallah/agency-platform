"""Merged duplicates point at their survivor (MST-3, decision A136).

``customers.merged_into_id`` and ``vendors.merged_into_id``: set on the
soft-deleted duplicate, so its history names the record it became.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0298
Revises: 20261003_0297
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0298"
down_revision: str | Sequence[str] | None = "20261003_0297"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("customers", "vendors")


def upgrade() -> None:
    """Add the column and its key where a store keeps the party."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "merged_into_id" in columns:
            continue
        op.add_column(table, sa.Column("merged_into_id", UUIDType(), nullable=True))
        op.create_foreign_key(
            f"FK_{table}_merged_into_id",
            table,
            table,
            ["merged_into_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "merged_into_id" in columns:
            op.drop_constraint(f"FK_{table}_merged_into_id", table, type_="foreignkey")
            op.drop_column(table, "merged_into_id")
