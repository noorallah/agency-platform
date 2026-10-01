"""The supplier's own credit note, recorded on a debit note (backlog 68 row 10).

* ``supplier_credit_note_number`` and ``supplier_credit_note_date`` on
  ``debit_notes``. NULL on every note written before them, and on a claim the
  firm raised itself.

The reason ``DISCOUNT`` needs nothing here: ``reason`` is a plain string.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0206"
down_revision: str | Sequence[str] | None = "20261001_0205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("supplier_credit_note_number", sa.String(80)),
    ("supplier_credit_note_date", sa.Date()),
)


def upgrade() -> None:
    """Add the two columns where the table exists and they do not."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("debit_notes"):
        return
    present = {column["name"] for column in inspector.get_columns("debit_notes")}
    for name, kind in _COLUMNS:
        if name not in present:
            op.add_column("debit_notes", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("debit_notes"):
        return
    present = {column["name"] for column in inspector.get_columns("debit_notes")}
    for name, _ in reversed(_COLUMNS):
        if name in present:
            op.drop_column("debit_notes", name)
