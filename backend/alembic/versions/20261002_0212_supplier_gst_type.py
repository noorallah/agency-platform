"""A supplier's GST type (backlog 78 row 2).

``vendors.gst_registration_type``: REGULAR, COMPOSITION, UNREGISTERED,
OVERSEAS or SEZ. NULL for every supplier already written, which keeps each as
it was: a GSTIN reads as REGULAR, none as UNREGISTERED.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0212
Revises: 20261002_0211
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0212"
down_revision: str | Sequence[str] | None = "20261002_0211"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(inspector: sa.Inspector) -> bool:
    """Say whether the store's suppliers already carry the column."""
    return any(
        column["name"] == "gst_registration_type"
        for column in inspector.get_columns("vendors")
    )


def upgrade() -> None:
    """Add the column where this store holds suppliers."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("vendors") or _has_column(inspector):
        return
    op.add_column(
        "vendors",
        sa.Column("gst_registration_type", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    """Drop the column where it exists."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("vendors") and _has_column(inspector):
        op.drop_column("vendors", "gst_registration_type")
