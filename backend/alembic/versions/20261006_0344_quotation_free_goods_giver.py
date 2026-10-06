"""A quotation line says whose free goods it shows.

``sales_quotation_lines.free_promotion_id`` -- the offer that gave a line
its free quantity, null where a person typed it. The sales order line has
carried the same since ``20261006_0335``; the quotation did not, so a
quotation of 24 pieces with 2 free given by an offer became an order of
"24, 2 free" that named no offer, claimed nothing and stood outside the
offer's budget (D-PRC-58). The conversion now leaves an offer's figure for
the order to work out afresh, and hands over only a typed one.

A bare id with no foreign key, as on the order line: an offer is retired by
soft delete and the line must go on naming it. Lines quoted before this
revision keep null, which reads as typed -- they convert as they always did,
until the quotation is saved again.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0344
Revises: 20261006_0343
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0344"
down_revision: str | Sequence[str] | None = "20261006_0343"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINES = "sales_quotation_lines"
_GIVER = "free_promotion_id"


def _has_column(inspector: sa.Inspector) -> bool | None:
    """Say whether the column is there, or None where the store has no table."""
    if not inspector.has_table(_LINES):
        return None
    return _GIVER in {column["name"] for column in inspector.get_columns(_LINES)}


def upgrade() -> None:
    """Add the column where the store keeps quotations."""
    if _has_column(sa.inspect(op.get_bind())) is False:
        op.add_column(_LINES, sa.Column(_GIVER, UUIDType(), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    if _has_column(sa.inspect(op.get_bind())) is True:
        op.drop_column(_LINES, _GIVER)
