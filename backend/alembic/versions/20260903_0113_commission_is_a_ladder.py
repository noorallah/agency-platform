"""Commission is a ladder, not a single rate.

A flat percentage is one arrangement of many. This adds the ladder, the two
things that decide how it reads (`slab_mode` and the cap), and the choice of
what the percentage is *of*.

Nothing changes meaning for a rule that already exists: `basis` defaults to
COLLECTED, which is what this module has always paid on, and a rule with no
slabs keeps paying its flat `percentage`.

Firm-owned, so the whole migration is skipped where `sales_invoices` is
absent, which is how a firm store is told apart from the platform schema --
the same marker `20260903_0111` uses. Deliberately **not** keyed on
`commission_rules`: the platform schema already holds a stray copy of that
table from before the module was firm-scoped, so keying on it would spread the
ladder into a store that does not trade. Every step also checks before it
acts, because firm schemas are partly built by `Base.metadata.create_all` and
can already hold what this adds.

Revision ID: 20260903_0113
Revises: 20260903_0112
Create Date: 2026-09-03

"""

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision = "20260903_0113"
down_revision = "20260903_0112"
branch_labels = None
depends_on = None

TABLE = "commission_rules"
SLABS = "commission_rule_slabs"


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the column names a table already has."""
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the ladder table and the three columns that shape it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sales_invoices") or not inspector.has_table(TABLE):
        return
    existing = _columns(inspector, TABLE)
    if "basis" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "basis",
                sa.String(length=20),
                nullable=False,
                server_default="COLLECTED",
            ),
        )
    if "slab_mode" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "slab_mode",
                sa.String(length=20),
                nullable=False,
                server_default="MARGINAL",
            ),
        )
    if "max_commission_amount" not in existing:
        op.add_column(
            TABLE,
            sa.Column("max_commission_amount", sa.Numeric(18, 2), nullable=True),
        )
    if inspector.has_table(SLABS):
        return
    op.create_table(
        SLABS,
        sa.Column("id", UUIDType(), nullable=False, primary_key=True),
        sa.Column("commission_rule_id", UUIDType(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("from_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("to_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("percentage", sa.Numeric(9, 4), nullable=False, server_default="0"),
        # The two defaults `Base.metadata.create_all` supplies and a
        # hand-written CREATE TABLE does not. Omitting them cost a real
        # NotNullViolation on the first insert against PostgreSQL while every
        # unit test stayed green, because the unit suite builds its schema
        # from the ORM and therefore never sees this table.
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["commission_rule_id"],
            [f"{TABLE}.id"],
            name="FK_commission_rule_slabs_commission_rule_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="CK_commission_rule_slabs_percentage_range",
        ),
        sa.CheckConstraint(
            "from_amount >= 0", name="CK_commission_rule_slabs_from_amount"
        ),
        sa.CheckConstraint(
            "to_amount IS NULL OR to_amount > from_amount",
            name="CK_commission_rule_slabs_band",
        ),
    )
    op.create_index(
        "IX_commission_rule_slabs_rule",
        SLABS,
        ["commission_rule_id", "from_amount"],
    )


def downgrade() -> None:
    """Drop the ladder and the columns that shape it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(SLABS):
        op.drop_index("IX_commission_rule_slabs_rule", table_name=SLABS)
        op.drop_table(SLABS)
    if not inspector.has_table(TABLE):
        return
    existing = _columns(inspector, TABLE)
    for column in ("max_commission_amount", "slab_mode", "basis"):
        if column in existing:
            op.drop_column(TABLE, column)
