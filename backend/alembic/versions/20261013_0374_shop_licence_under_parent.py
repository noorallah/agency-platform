"""A firm may ask each shop for its own licence (backlog 139, row F8).

``trade_licence_settings.shop_needs_own_licence``: off, a shop under a parent
buyer that holds no licence of a type is covered by its parent's, and a
supplier's branch by its main office's; on, each is judged on its own alone.
Off for every firm, which is the owner's decision of 2026-10-13.

Nothing else moves: no licence, no document and no other setting is touched.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the column is
added only where ``trade_licence_settings`` exists and lacks it, because a
firm store is partly built by ``Base.metadata.create_all``.

Revision ID: 20261013_0374
Revises: 20261013_0373
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0374"
down_revision: str | Sequence[str] | None = "20261013_0373"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "trade_licence_settings"
_COLUMN = "shop_needs_own_licence"


def _has_column() -> bool | None:
    """Say whether the column is there; None where the table is not."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return None
    return _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    """Add the switch, off for every firm."""
    if _has_column() is False:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    """Drop the switch."""
    if _has_column():
        op.drop_column(_TABLE, _COLUMN)
