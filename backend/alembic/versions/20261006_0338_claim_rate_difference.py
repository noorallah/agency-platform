"""A principal's price cut reaches the claim: rate difference on stock in hand.

``principal_claims.rate_difference_amount`` -- the part of a claim that is a
price cut on the stock held when it took effect. Zero on every claim raised
before this revision, none of which held any.

``principal_claim_lines.batch_id``, ``old_rate`` and ``new_rate`` -- the batch
the stock was in, and the purchase rate per stock unit before and after the
cut, as the claim stated them. Null on every line of another kind. The batch
is a bare id with no foreign key, as the line's ``source_id`` is.

No new table and no new control account: the claim credits the purchase
price variance account every firm already maps.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0338
Revises: 20261006_0337
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0338"
down_revision: str | Sequence[str] | None = "20261006_0337"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLAIMS = "principal_claims"
_TOTAL = "rate_difference_amount"
_LINES = "principal_claim_lines"
_BATCH, _OLD, _NEW = "batch_id", "old_rate", "new_rate"


def _columns(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return a table's column names, or None where the store has no such table."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the four columns where the store keeps claims."""
    inspector = sa.inspect(op.get_bind())
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _TOTAL not in claims:
        op.add_column(
            _CLAIMS,
            sa.Column(
                _TOTAL, sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")
            ),
        )
    lines = _columns(inspector, _LINES)
    if lines is None:
        return
    if _BATCH not in lines:
        op.add_column(_LINES, sa.Column(_BATCH, UUIDType(), nullable=True))
    for rate in (_OLD, _NEW):
        if rate not in lines:
            op.add_column(_LINES, sa.Column(rate, sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    """Drop the four columns."""
    inspector = sa.inspect(op.get_bind())
    lines = _columns(inspector, _LINES)
    for column in (_NEW, _OLD, _BATCH):
        if lines is not None and column in lines:
            op.drop_column(_LINES, column)
    claims = _columns(inspector, _CLAIMS)
    if claims is not None and _TOTAL in claims:
        op.drop_column(_CLAIMS, _TOTAL)
