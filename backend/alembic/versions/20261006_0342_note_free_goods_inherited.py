"""A delivery note line says whether its free goods were typed or inherited.

``delivery_note_lines.free_quantity_inherited`` -- true where the note said
nothing about free goods and took the order line's share. Such a line is
settled again when the note is approved, from what the notes approved before
it already took, so two drafts of one order line ship the order's free goods
between them whatever order they were typed in (D-PRC-29). A typed figure --
a zero included -- stands, and is never worked again.

False on every existing line: nothing recorded which were typed, and a typed
zero must not start shipping goods. A draft saved again records it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0342
Revises: 20261006_0341
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0342"
down_revision: str | Sequence[str] | None = "20261006_0341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "delivery_note_lines"
_COLUMN = "free_quantity_inherited"


def upgrade() -> None:
    """Add the column where the store keeps delivery notes."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
