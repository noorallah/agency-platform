"""Let a firm say which sales stages it fills in by hand.

The chain is quotation, sales order, delivery note, invoice. A firm run by one
person has no use for the first three -- four screens for one counter sale --
so this records which of them that firm raises itself and which the services
synthesise on its behalf.

A column per stage rather than one ``mode``, because a firm changes shape:
somebody trading alone hires a salesman, then a warehouse hand, and each step
should be a switch rather than a migration.

Every stage defaults to on and no row is created for anybody, so a firm that
has never configured this behaves exactly as it did before the table existed.
No backfill, and no firm's screens move because of an upgrade.

``sales_workflow_settings`` is firm-owned, so it belongs in every firm store and
not in ``platform``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260902_0104"
down_revision: str | Sequence[str] | None = "20260823_0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_workflow_settings"


def upgrade() -> None:
    """Create the per-firm sales stage configuration table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: sales orders live in firm stores, so platform has no chain to
    # configure and gets no table.
    if not inspector.has_table("sales_orders"):
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "quotation_stage",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "sales_order_stage",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "delivery_note_stage",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("default_branch_id", UUIDType(), nullable=True),
        sa.Column("default_warehouse_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_sales_workflow_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_sales_workflow_settings_firm"),
    )
    op.create_index("IX_sales_workflow_settings_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the table; every firm falls back to the whole chain."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    op.drop_index("IX_sales_workflow_settings_firm_id", table_name=_TABLE)
    op.drop_table(_TABLE)
