"""Give the by-salesman reports something to be measured against.

They have always answered "how much" and never "how much against what",
because there was nothing to compare them to. `sales_targets` is that missing
half.

Two things are configuration rather than a decision baked in. `basis` is
INVOICED or COLLECTED, because firms genuinely differ about what counts as
sold. And the period is given as dates rather than derived from a name: a
firm's quarter does not always start where the calendar's does, and a window
computed from "Q1" would be wrong for every firm whose year starts in April.

Firm-owned, so `firm_id` carries no foreign key and the platform schema gets
nothing. The two scope references are guarded: `users` lives only in the
platform schema, so a target may name a salesman without being able to point
at one.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0111"
down_revision: str | Sequence[str] | None = "20260903_0110"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_targets"


def upgrade() -> None:
    """Create the target table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: sales invoices live in firm stores, so platform has nothing
    # to measure and gets no table.
    if not inspector.has_table("sales_invoices"):
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
        sa.Column("salesman_id", UUIDType(), nullable=True),
        sa.Column("territory_id", UUIDType(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "period_type",
            sa.String(length=20),
            server_default="MONTHLY",
            nullable=False,
        ),
        sa.Column(
            "basis", sa.String(length=20), server_default="INVOICED", nullable=False
        ),
        sa.Column(
            "target_amount", sa.Numeric(18, 2), server_default="0", nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="ACTIVE", nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_sales_targets"),
        sa.UniqueConstraint(
            "firm_id",
            "salesman_id",
            "territory_id",
            "period_start",
            name="UQ_sales_targets_scope_period",
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name="CK_sales_targets_period_order"
        ),
        sa.CheckConstraint("target_amount >= 0", name="CK_sales_targets_amount"),
    )
    op.create_index("IX_sales_targets_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_sales_targets_firm_period", _TABLE, ["firm_id", "period_start"])
    op.create_index(
        "IX_sales_targets_firm_salesman", _TABLE, ["firm_id", "salesman_id"]
    )
    # Declared only where the target exists. `users` is platform-only, so a
    # firm store cannot reference it -- the guarded-FK rule this repo records.
    if inspector.has_table("sales_territories"):
        op.create_foreign_key(
            "FK_sales_targets_territory_id",
            _TABLE,
            "sales_territories",
            ["territory_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Drop the target table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
