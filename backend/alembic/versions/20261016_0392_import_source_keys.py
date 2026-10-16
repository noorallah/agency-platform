"""An old software's number kept against our record (Swathi plan, gap G2).

``import_source_keys``: one row per record a conversion brought in -- the
program it came from, what kind of record, that program's own number for it
and our row's id -- so a second run of the same conversion recognises the
record and skips it. A live key is unique per firm, program and subject.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261016_0392
Revises: 20261016_0391
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261016_0392"
down_revision: str | Sequence[str] | None = "20261016_0391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "import_source_keys"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    # A firm store holds products; the platform store has no imports.
    if not inspector.has_table("products") or inspector.has_table(_TABLE):
        return
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
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(40), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("record_id", UUIDType(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_import_source_keys"),
    )
    op.create_index("IX_import_source_keys_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_import_source_keys_record_id", _TABLE, ["record_id"])
    op.create_index(
        "UQ_import_source_keys_firm_system_subject_key_active",
        _TABLE,
        ["firm_id", "source_system", "subject", "source_key"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    """Drop the table; a later run can no longer tell what it brought in."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
