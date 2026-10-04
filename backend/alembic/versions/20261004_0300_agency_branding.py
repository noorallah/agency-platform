"""The agency's branding: name, tagline, accent colour and logo (backlog 71, U2).

One live row per installation, in the **platform** store only: sign-in shows
the agency before any firm is chosen, so it cannot live in a firm's store.
The identity tables are how a platform target is recognised, as in
``20260811_0065`` -- ``alembic/env.py`` runs every revision against every
store, and without the guard each firm store would grow an unused copy.

``PLATFORM_SETTINGS``, which the writes need, is already seeded.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261004_0300"
down_revision: str | Sequence[str] | None = "20261004_0299"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agency_branding"


def upgrade() -> None:
    """Create the branding table in the platform store."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    if inspector.has_table(_TABLE):
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "branding_key", sa.String(16), server_default="AGENCY", nullable=False
        ),
        sa.Column("agency_name", sa.String(150), nullable=False),
        sa.Column("tagline", sa.String(200), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("logo", sa.LargeBinary(), nullable=True),
        sa.Column("logo_content_type", sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint("id", name=f"PK_{_TABLE}"),
    )
    op.create_index(
        "UQ_agency_branding_key_active",
        _TABLE,
        ["branding_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    """Drop the branding table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
