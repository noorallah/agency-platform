"""Free goods on a bill reach the claim to the principal.

``sales_order_lines.free_promotion_id`` -- the offer that gave a line its
free quantity, null where a person typed it. A bare id with no foreign key:
an offer is retired by soft delete and the line must go on naming it. Lines
written before this revision keep null, which reads as typed: nothing
recorded whose free goods they were.

``principal_claims.free_goods_amount`` -- the part of a claim that is free
goods typed on lines of the principal's products, at dispatch cost. Zero on
every claim raised before this revision, none of which held any.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0335
Revises: 20261006_0334
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0335"
down_revision: str | Sequence[str] | None = "20261006_0334"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINES = "sales_order_lines"
_GIVER = "free_promotion_id"
_CLAIMS = "principal_claims"
_GOODS = "free_goods_amount"


def _columns(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return a table's column names, or None where the store has no such table."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the two columns where the store keeps orders and claims."""
    inspector = sa.inspect(op.get_bind())
    lines = _columns(inspector, _LINES)
    if lines is not None and _GIVER not in lines:
        op.add_column(_LINES, sa.Column(_GIVER, UUIDType(), nullable=True))
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _GOODS not in claims:
        op.add_column(
            _CLAIMS,
            sa.Column(
                _GOODS, sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")
            ),
        )


def downgrade() -> None:
    """Drop the two columns."""
    inspector = sa.inspect(op.get_bind())
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _GOODS in claims:
        op.drop_column(_CLAIMS, _GOODS)
    lines = _columns(inspector, _LINES)
    if lines is not None and _GIVER in lines:
        op.drop_column(_LINES, _GIVER)
