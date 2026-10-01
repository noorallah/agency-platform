"""Transport details on the delivery note (backlog 67 row 5).

``delivery_notes.transporter_name``, ``transporter_gstin``,
``transport_mode`` (ROAD / RAIL / AIR / SHIP), ``lr_number``, ``lr_date`` and
``distance_km``, beside the existing vehicle and driver: what Part B of an
e-way bill asks for, printed on the challan and read by the e-way bill when a
field is left blank. NULL on every existing note.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0197"
down_revision: str | Sequence[str] | None = "20261001_0196"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    ("transporter_name", sa.String(200)),
    ("transporter_gstin", sa.String(15)),
    ("transport_mode", sa.String(10)),
    ("lr_number", sa.String(60)),
    ("lr_date", sa.Date()),
    ("distance_km", sa.Integer()),
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
