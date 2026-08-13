"""Let a purchase return name the batch it is sending back.

``purchase_return_lines.batch_number`` is free text -- what was read off the
carton being crated up for the supplier. ``batches`` is a keyed register.
Nothing joined them, so goods could arrive in a batch and leave to a customer
from one, while the return to the vendor still came off the product's untracked
stock: the batch's own row kept quantity that had physically left the building.

``purchase_return_lines.batch_id`` records what the typed number resolved to,
the way ``goods_receipt_lines`` and ``delivery_note_lines`` already do
(``20260813_0071``).

Unlike a receipt, a return never creates the batch. Goods that have physically
arrived have to be receivable, so an unknown number on a receipt is registered;
an unknown number on a return is a number nobody ever received, and inventing a
batch for it would write stock history that did not happen.

The text column stays. It is what was written on the paperwork.

``purchase_return_lines`` is firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260813_0072"
down_revision: str | Sequence[str] | None = "20260813_0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_return_lines"


def upgrade() -> None:
    """Point the return line at the batch register."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return  # platform schema: firm-owned tables are not there.
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "batch_id" in columns:
        return
    op.add_column(_TABLE, sa.Column("batch_id", UUIDType(), nullable=True))
    op.create_foreign_key(
        f"FK_{_TABLE}_batch_id",
        _TABLE,
        "batches",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(f"IX_{_TABLE}_batch_id", _TABLE, ["batch_id"])


def downgrade() -> None:
    """Return the line to carrying only the typed number."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if "batch_id" not in columns:
        return
    if f"IX_{_TABLE}_batch_id" in {
        index["name"] for index in inspector.get_indexes(_TABLE)
    }:
        op.drop_index(f"IX_{_TABLE}_batch_id", table_name=_TABLE)
    op.drop_constraint(f"FK_{_TABLE}_batch_id", _TABLE, type_="foreignkey")
    op.drop_column(_TABLE, "batch_id")
