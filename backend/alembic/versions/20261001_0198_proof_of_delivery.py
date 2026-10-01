"""Proof of delivery on the delivery note (backlog 67 row 6).

``delivery_notes.delivered_at`` (when the customer received the goods),
``delivery_received_by``, ``delivery_remarks``, ``delivery_recorded_at`` and
``delivery_recorded_by``. A flag beside the status rather than a new status:
a note is delivered when ``delivered_at`` is set, which only a recorded proof
does. NULL on every existing note -- none was ever proven delivered.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0198"
down_revision: str | Sequence[str] | None = "20261001_0197"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    ("delivered_at", sa.DateTime(timezone=True)),
    ("delivery_received_by", sa.String(120)),
    ("delivery_remarks", sa.Text()),
    ("delivery_recorded_at", sa.DateTime(timezone=True)),
    ("delivery_recorded_by", UUIDType()),
)


def upgrade() -> None:
    """Add the columns where delivery notes live."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("delivery_notes"):
        return
    present = {item["name"] for item in inspector.get_columns("delivery_notes")}
    for name, kind in _COLUMNS:
        if name not in present:
            op.add_column("delivery_notes", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("delivery_notes"):
        return
    present = {item["name"] for item in inspector.get_columns("delivery_notes")}
    for name, _ in reversed(_COLUMNS):
        if name in present:
            op.drop_column("delivery_notes", name)
