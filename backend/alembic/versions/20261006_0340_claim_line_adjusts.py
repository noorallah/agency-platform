"""A claim line can take back part of an earlier claim's line.

``principal_claim_lines.adjusts_line_id`` -- on a negative line, the earlier
claim's line it reduces: goods or a discount that came back after that claim
was raised come off the next claim on the principal (D-PRC-31). Null on every
existing line, none of which is an adjustment. A bare id with no foreign key,
as the line's ``source_id`` is.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0340
Revises: 20261006_0339
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0340"
down_revision: str | Sequence[str] | None = "20261006_0339"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINES = "principal_claim_lines"
_ADJUSTS = "adjusts_line_id"
_INDEX = "IX_principal_claim_lines_adjusts"


def _columns(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return a table's column names, or None where the store has no such table."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the column and its index where the store keeps claims."""
    inspector = sa.inspect(op.get_bind())
    lines = _columns(inspector, _LINES)
    if lines is None:
        return
    if _ADJUSTS not in lines:
        op.add_column(_LINES, sa.Column(_ADJUSTS, UUIDType(), nullable=True))
    if _INDEX not in {index["name"] for index in inspector.get_indexes(_LINES)}:
        op.create_index(_INDEX, _LINES, [_ADJUSTS])


def downgrade() -> None:
    """Drop the index and the column."""
    inspector = sa.inspect(op.get_bind())
    lines = _columns(inspector, _LINES)
    if lines is None:
        return
    if _INDEX in {index["name"] for index in inspector.get_indexes(_LINES)}:
        op.drop_index(_INDEX, table_name=_LINES)
    if _ADJUSTS in lines:
        op.drop_column(_LINES, _ADJUSTS)
