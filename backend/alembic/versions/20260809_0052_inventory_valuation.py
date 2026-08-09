"""Give inventory a cost, so stock can be valued.

``stock_ledger_entries`` recorded quantity buckets and no cost of any kind: no
unit cost, no value, no running average. Stock could not be valued, cost of
goods sold did not exist, and neither gross margin nor a balance sheet was
reachable no matter what the finance module did.

This adds the cost of each movement to the ledger and a per-firm, per-product
running valuation. The grain is deliberately ``(firm, product)`` rather than per
location: a per-warehouse average turns every stock transfer into a
cost-movement problem, and a per-bin average is noise. ``costing_method`` is
stored so a firm can move to FIFO later without reshaping the table.

No backfill. Movements recorded before this revision have no cost, which is what
null means here; the running average starts from the first priced receipt.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0052"
down_revision: str | Sequence[str] | None = "20260809_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_COLUMNS = (
    ("unit_cost", sa.Numeric(18, 6)),
    ("total_cost", sa.Numeric(18, 4)),
    ("average_cost_after", sa.Numeric(18, 6)),
)


def upgrade() -> None:
    """Add ledger cost columns and the product valuation state."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("stock_ledger_entries"):
        present = {c["name"] for c in inspector.get_columns("stock_ledger_entries")}
        for name, column_type in LEDGER_COLUMNS:
            if name not in present:
                op.add_column(
                    "stock_ledger_entries", sa.Column(name, column_type, nullable=True)
                )

    if inspector.has_table("product_valuations"):
        return

    # firms lives only in the platform schema; products is firm-owned. Declare
    # each reference only where the target is actually present.
    constraints: list[sa.schema.SchemaItem] = []
    if inspector.has_table("firms"):
        constraints.append(sa.ForeignKeyConstraint(["firm_id"], ["firms.id"]))
    if inspector.has_table("products"):
        constraints.append(
            sa.ForeignKeyConstraint(
                ["product_id"], ["products.id"], ondelete="RESTRICT"
            )
        )

    op.create_table(
        "product_valuations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "costing_method",
            sa.String(length=30),
            nullable=False,
            server_default="WEIGHTED_AVERAGE",
        ),
        sa.Column(
            "quantity_on_hand", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "average_cost", sa.Numeric(18, 6), nullable=False, server_default="0"
        ),
        sa.Column("total_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        *constraints,
        sa.PrimaryKeyConstraint("id", name="PK_product_valuations"),
        sa.UniqueConstraint(
            "firm_id", "product_id", name="UQ_product_valuations_firm_product"
        ),
    )
    op.create_index(
        "IX_product_valuations_firm_product",
        "product_valuations",
        ["firm_id", "product_id"],
    )
    op.create_index("IX_product_valuations_firm_id", "product_valuations", ["firm_id"])


def downgrade() -> None:
    """Drop the valuation state and the ledger cost columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("product_valuations"):
        op.drop_table("product_valuations")

    if inspector.has_table("stock_ledger_entries"):
        present = {c["name"] for c in inspector.get_columns("stock_ledger_entries")}
        for name, _ in LEDGER_COLUMNS:
            if name in present:
                op.drop_column("stock_ledger_entries", name)
