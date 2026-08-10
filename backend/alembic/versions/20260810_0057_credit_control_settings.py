"""Give credit limits a policy to be enforced by.

``customers.credit_limit`` existed from the beginning and constrained nothing:
sales orders snapshotted it and no code compared it with what the customer
owed. Whether a breach should warn or block is a firm's decision, so it needs
somewhere to live.

One row per firm, the shape ``tax_settings`` already uses. Firms with no row
fall back to the service default -- WARN at 80% -- so this migration creates the
table and nothing else: no backfill, and no firm has its trading stopped by an
upgrade.

``credit_control_settings`` is firm-owned, so it belongs in every firm store and
not in ``platform``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260810_0057"
down_revision: str | Sequence[str] | None = "20260809_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "credit_control_settings"


def upgrade() -> None:
    """Create the per-firm credit policy table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: customers live in firm stores, so platform has no customers
    # to police and gets no table.
    if not inspector.has_table("customers"):
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
            "enforcement",
            sa.String(length=10),
            server_default="WARN",
            nullable=False,
        ),
        sa.Column(
            "warn_at_percent",
            sa.Numeric(5, 2),
            server_default="80",
            nullable=False,
        ),
        sa.Column(
            "block_at_percent",
            sa.Numeric(5, 2),
            server_default="100",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="PK_credit_control_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_credit_control_settings_firm"),
    )
    op.create_index("IX_credit_control_settings_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the policy table; firms fall back to the service default."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    op.drop_index("IX_credit_control_settings_firm_id", table_name=_TABLE)
    op.drop_table(_TABLE)
