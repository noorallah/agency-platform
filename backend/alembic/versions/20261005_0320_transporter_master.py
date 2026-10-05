"""The transporter master, and the carrier and freight terms on a note.

Backlog §87 #5 (SG-5).

* ``transporters``: the firm's carriers -- name, GSTIN or TRANSIN, phone,
  usual mode -- one live row per name.
* ``delivery_notes.transporter_id``: the carrier a note chose. The note keeps
  its own name, id and mode columns, which choosing a carrier fills.
* ``delivery_notes.freight_terms``: PAID, TO_PAY or TO_BE_BILLED.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each object is
made only in a store that holds delivery notes and lacks it.

Revision ID: 20261005_0320
Revises: 20261005_0319
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0320"
down_revision: str | Sequence[str] | None = "20261005_0319"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "transporters"
_NOTES = "delivery_notes"
_UNIQUE = "UQ_transporters_firm_name_active"
_FK = "FK_delivery_notes_transporter_id"


def _create_transporters() -> None:
    """Create the master, with the columns every ``BaseEntity`` table carries."""
    op.create_table(
        _TABLE,
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("transporter_ref", sa.String(15), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("default_mode", sa.String(10), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_transporters"),
    )
    op.create_index("IX_transporters_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        _UNIQUE,
        _TABLE,
        ["firm_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def upgrade() -> None:
    """Create the master and add the note's two columns where missing."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no delivery notes.
    if not inspector.has_table(_NOTES):
        return
    if not inspector.has_table(_TABLE):
        _create_transporters()
    present = {column["name"] for column in inspector.get_columns(_NOTES)}
    if "transporter_id" not in present:
        op.add_column(_NOTES, sa.Column("transporter_id", UUIDType(), nullable=True))
        op.create_foreign_key(
            _FK, _NOTES, _TABLE, ["transporter_id"], ["id"], ondelete="RESTRICT"
        )
    if "freight_terms" not in present:
        op.add_column(_NOTES, sa.Column("freight_terms", sa.String(15), nullable=True))


def downgrade() -> None:
    """Drop the note's two columns and the master where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_NOTES):
        present = {column["name"] for column in inspector.get_columns(_NOTES)}
        if "freight_terms" in present:
            op.drop_column(_NOTES, "freight_terms")
        if "transporter_id" in present:
            if _FK in {key["name"] for key in inspector.get_foreign_keys(_NOTES)}:
                op.drop_constraint(_FK, _NOTES, type_="foreignkey")
            op.drop_column(_NOTES, "transporter_id")
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
