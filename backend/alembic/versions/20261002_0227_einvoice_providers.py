"""How a firm registers its e-invoices: the provider (decision A42).

* ``einvoice_settings``: one row per firm naming its route -- SANDBOX (the
  default; nothing is filed), OFFLINE (the portal's bulk upload, by hand),
  and later NIC_DIRECT and GSP.
* ``einvoice_registrations.provider``: the route each registration took.
  Rows from before were all the sandbox, so they are stamped SANDBOX.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0227
Revises: 20261002_0226
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0227"
down_revision: str | Sequence[str] | None = "20261002_0226"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = "einvoice_settings"
_REGISTRATIONS = "einvoice_registrations"


def upgrade() -> None:
    """Create the settings table and stamp each registration's route."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_REGISTRATIONS):
        return
    if not inspector.has_table(_SETTINGS):
        op.create_table(
            _SETTINGS,
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
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column(
                "provider", sa.String(20), server_default="SANDBOX", nullable=False
            ),
            sa.PrimaryKeyConstraint("id", name="PK_einvoice_settings"),
        )
        op.create_index("IX_einvoice_settings_firm_id", _SETTINGS, ["firm_id"])
        op.create_index(
            "UQ_einvoice_settings_firm_active",
            _SETTINGS,
            ["firm_id"],
            unique=True,
            postgresql_where=sa.text("NOT is_deleted"),
            sqlite_where=sa.text("NOT is_deleted"),
        )
    columns = {column["name"] for column in inspector.get_columns(_REGISTRATIONS)}
    if "provider" not in columns:
        op.add_column(
            _REGISTRATIONS, sa.Column("provider", sa.String(20), nullable=True)
        )
        # Every registration so far was a rehearsal.
        op.execute(
            sa.text(
                f"UPDATE {_REGISTRATIONS} SET provider = 'SANDBOX' "
                "WHERE provider IS NULL AND mode = 'SANDBOX'"
            )
        )


def downgrade() -> None:
    """Drop the provider column and the settings table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_REGISTRATIONS) and "provider" in {
        column["name"] for column in inspector.get_columns(_REGISTRATIONS)
    }:
        op.drop_column(_REGISTRATIONS, "provider")
    if inspector.has_table(_SETTINGS):
        op.drop_table(_SETTINGS)
