"""A sales order can be stopped without being cancelled.

A firm needs to say "not yet" to an order -- a dispute, a document the customer
has not sent, a delivery they asked to defer -- without unwinding it. Until now
the only ways to stop one were to cancel it, which gives the stock back and
ends the deal, or to remember not to dispatch it.

**A hold is a flag, not a status, and that is the whole design.** An order that
is PARTIALLY_DELIVERED can be held, and releasing it has to put it back to
PARTIALLY_DELIVERED -- not to APPROVED. Writing HOLD into `status` would destroy
the only record of how far the order had got, and the release would then have to
guess. Nothing is overwritten here, so nothing has to be restored. That is the
same reasoning `update_order` was fixed on in 2026-08-18, where a status written
from a request body silently reset an approved order.

Every column defaults to "not held", so no existing order changes behaviour.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0122
Revises: 20260903_0121
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0122"
down_revision: str | Sequence[str] | None = "20260903_0121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_orders"

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object], object], ...] = (
    ("is_on_hold", sa.Boolean(), "false"),
    ("hold_reason", sa.Text(), None),
    ("held_at", sa.DateTime(timezone=True), None),
    ("held_by", UUIDType(), None),
    ("released_at", sa.DateTime(timezone=True), None),
    ("released_by", UUIDType(), None),
)


def upgrade() -> None:
    """Add the hold columns where a firm store lacks them.

    Checked one at a time rather than assumed absent: firm schemas are partly
    built by `Base.metadata.create_all` from the sample-data and tenancy-reset
    scripts, so a column can already exist even when `alembic_version` reads
    older.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name, kind, default in _COLUMNS:
        if name in existing:
            continue
        op.add_column(
            _TABLE,
            sa.Column(
                name,
                kind,
                nullable=(name != "is_on_hold"),
                server_default=None if default is None else sa.text(str(default)),
            ),
        )


def downgrade() -> None:
    """Drop the hold columns, releasing everything that was held."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for name, _kind, _default in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
