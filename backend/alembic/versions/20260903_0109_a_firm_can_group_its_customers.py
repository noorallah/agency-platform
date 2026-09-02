"""Let a firm group the customers it sells to.

`customers.customer_type` is INDIVIDUAL or BUSINESS -- a legal classification,
and the wrong thing to hang a price or an offer on. A firm that wants to give
wholesalers a different rate needs a grouping of its own choosing, and until
now there was none: the only thing that could be targeted was one shop or a
whole territory.

A flat list rather than a hierarchy. `sales_territories` is already a tree, and
a second one would leave two answers to "which group is this customer in".

Nothing is assigned by this migration. A firm that does not segment its
customers keeps a null on every one of them, and the pricing chain reads that
as no arrangement -- so no existing document changes price.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0109"
down_revision: str | Sequence[str] | None = "20260903_0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customer_groups"


def upgrade() -> None:
    """Create the segment master and point customers at it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: customers live in firm stores, so platform gets nothing.
    if not inspector.has_table("customers"):
        return

    if not inspector.has_table(_TABLE):
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
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "default_discount_percent",
                sa.Numeric(9, 4),
                server_default="0",
                nullable=False,
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_customer_groups"),
            sa.UniqueConstraint("firm_id", "code", name="UQ_customer_groups_firm_code"),
            sa.UniqueConstraint("firm_id", "name", name="UQ_customer_groups_firm_name"),
        )
        op.create_index("IX_customer_groups_firm_id", _TABLE, ["firm_id"])
        op.create_index(
            "IX_customer_groups_firm_status", _TABLE, ["firm_id", "is_active"]
        )

    columns = {column["name"] for column in inspector.get_columns("customers")}
    if "customer_group_id" not in columns:
        # Nullable, and left null everywhere: a firm that does not segment its
        # customers should not be made to invent a group to hold all of them,
        # and the pricing chain reads null as no arrangement.
        op.add_column(
            "customers", sa.Column("customer_group_id", UUIDType(), nullable=True)
        )
        op.create_index(
            "IX_customers_customer_group_id", "customers", ["customer_group_id"]
        )
        op.create_foreign_key(
            "FK_customers_customer_group_id",
            "customers",
            _TABLE,
            ["customer_group_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Unpoint the customers, then drop the master."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("customers"):
        columns = {column["name"] for column in inspector.get_columns("customers")}
        if "customer_group_id" in columns:
            op.drop_constraint(
                "FK_customers_customer_group_id", "customers", type_="foreignkey"
            )
            op.drop_index("IX_customers_customer_group_id", table_name="customers")
            op.drop_column("customers", "customer_group_id")
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
