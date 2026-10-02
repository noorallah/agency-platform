"""The firm's UPI ID on its print template (MSG-2, decision A55).

`document_print_templates.upi_id` is the address a customer pays into by
scanning the bill. It sits beside `bank_details` because it is the same kind
of fact -- where the money goes -- and is printed in the same block. Blank
means no QR, so every existing template prints as before.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0240
Revises: 20261003_0239
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0240"
down_revision: str | Sequence[str] | None = "20261003_0239"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_print_templates"
_COLUMN = "upi_id"


def upgrade() -> None:
    """Add the UPI ID, where the template table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(255), nullable=True))


def downgrade() -> None:
    """Drop the UPI ID."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
