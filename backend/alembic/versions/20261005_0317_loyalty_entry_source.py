"""Loyalty entries name the return or credit note that moved them (D-SELL-47).

* ``loyalty_entries.source_type`` and ``.source_id``: the sales return or
  credit note that took points back off a bill's earning, so cancelling that
  document can find what it took and give it back. Null on every other entry.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where the table exists and lacks it.

Revision ID: 20261005_0317
Revises: 20261005_0316
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0317"
down_revision: str | Sequence[str] | None = "20261005_0316"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "loyalty_entries"
_INDEX = "IX_loyalty_entries_firm_source"


def upgrade() -> None:
    """Add the two columns and their index where the store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "source_type" not in present:
        op.add_column(_TABLE, sa.Column("source_type", sa.String(30)))
    if "source_id" not in present:
        op.add_column(_TABLE, sa.Column("source_id", UUIDType()))
    if _INDEX not in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["firm_id", "source_type", "source_id"])


def downgrade() -> None:
    """Drop the index and the two columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _INDEX in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in ("source_id", "source_type"):
        if column in present:
            op.drop_column(_TABLE, column)
