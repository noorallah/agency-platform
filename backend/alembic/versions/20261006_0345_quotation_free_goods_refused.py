"""A quotation line says when "0 free" was typed on it.

``sales_quotation_lines.free_goods_refused`` -- true where a person typed a
free quantity of 0, which refuses an offer's free goods on that line. The
line's ``free_quantity`` is 0 there, and 0 as well where nothing was said and
no offer gave anything, so the conversion could not tell a refusal from
silence and handed the order silence for both: a quotation that showed
nothing free became an order with the offer's 2 free, claimed at approval
(D-PRC-68). The conversion now hands the order the typed 0.

Lines quoted before this revision read false, which is silence -- they
convert as they always did, until the quotation is saved again.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0345
Revises: 20261006_0344
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0345"
down_revision: str | Sequence[str] | None = "20261006_0344"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LINES = "sales_quotation_lines"
_REFUSED = "free_goods_refused"


def _has_column(inspector: sa.Inspector) -> bool | None:
    """Say whether the column is there, or None where the store has no table."""
    if not inspector.has_table(_LINES):
        return None
    return _REFUSED in {column["name"] for column in inspector.get_columns(_LINES)}


def upgrade() -> None:
    """Add the column where the store keeps quotations."""
    if _has_column(sa.inspect(op.get_bind())) is False:
        op.add_column(
            _LINES,
            sa.Column(
                _REFUSED, sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    """Drop the column."""
    if _has_column(sa.inspect(op.get_bind())) is True:
        op.drop_column(_LINES, _REFUSED)
