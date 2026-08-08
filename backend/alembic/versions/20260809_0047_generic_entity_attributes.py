"""Make configurable attributes generic across modules.

``attribute_definitions`` could only describe product extensions: it had no way
to say which record a field belongs to, and its scoping columns referenced
product categories. Values had two homes — a typed ``product_attribute_values``
table that no code ever wrote, and a ``products.category_attribute_values`` JSON
column that could not be indexed or filtered.

This revision gives definitions an ``entity_type`` and rebuilds
``product_attribute_values`` from the shared ``AttributeValueMixin``, so the
value keeps a real foreign key to its product while the behaviour stays generic
through a parameterised service. The JSON column is removed. Neither store held
data at the time of writing, so nothing is migrated.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0047"
down_revision: str | Sequence[str] | None = "20260809_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column[object]]:
    """Return the shared BaseEntity columns."""
    return [
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
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    """Add entity targeting, create the shared value table, drop the old stores."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("attribute_definitions"):
        columns = {c["name"] for c in inspector.get_columns("attribute_definitions")}
        if "entity_type" not in columns:
            op.add_column(
                "attribute_definitions",
                sa.Column(
                    "entity_type",
                    sa.String(length=50),
                    nullable=False,
                    server_default="PRODUCT",
                ),
            )
            op.create_index(
                "IX_attribute_definitions_entity_type",
                "attribute_definitions",
                ["entity_type"],
            )

    # The dead, never-written product table is rebuilt from the shared mixin.
    if inspector.has_table("product_attribute_values"):
        op.drop_table("product_attribute_values")
    if inspector.has_table("entity_attribute_values"):
        op.drop_table("entity_attribute_values")

    if inspector.has_table("products"):
        firm_fk = (
            [sa.ForeignKeyConstraint(["firm_id"], ["firms.id"])]
            if inspector.has_table("firms")
            else []
        )
        attribute_fk = (
            [
                sa.ForeignKeyConstraint(
                    ["attribute_definition_id"],
                    ["attribute_definitions.id"],
                    ondelete="RESTRICT",
                )
            ]
            if inspector.has_table("attribute_definitions")
            else []
        )
        op.create_table(
            "product_attribute_values",
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column("product_id", sa.Uuid(), nullable=False),
            sa.Column("attribute_definition_id", sa.Uuid(), nullable=False),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Numeric(18, 6), nullable=True),
            sa.Column("value_date", sa.Date(), nullable=True),
            sa.Column("value_boolean", sa.Boolean(), nullable=True),
            *firm_fk,
            *attribute_fk,
            sa.ForeignKeyConstraint(
                ["product_id"], ["products.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "product_id",
                "attribute_definition_id",
                name="UQ_product_attribute_values_product_attribute",
            ),
        )
        for name, columns in (
            ("IX_product_attribute_values_firm_id", ["firm_id"]),
            ("IX_product_attribute_values_product_id", ["product_id"]),
            (
                "IX_product_attribute_values_attribute_definition_id",
                ["attribute_definition_id"],
            ),
            ("IX_product_attribute_values_firm_text", ["firm_id", "value_text"]),
            ("IX_product_attribute_values_firm_number", ["firm_id", "value_number"]),
            ("IX_product_attribute_values_firm_date", ["firm_id", "value_date"]),
        ):
            op.create_index(name, "product_attribute_values", columns)

    if inspector.has_table("products"):
        columns = {c["name"] for c in inspector.get_columns("products")}
        if "category_attribute_values" in columns:
            op.drop_column("products", "category_attribute_values")


def downgrade() -> None:
    """Drop the shared value table and restore the product JSON column."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("product_attribute_values"):
        op.drop_table("product_attribute_values")
    if inspector.has_table("attribute_definitions"):
        columns = {c["name"] for c in inspector.get_columns("attribute_definitions")}
        if "entity_type" in columns:
            op.drop_column("attribute_definitions", "entity_type")
    if inspector.has_table("products"):
        columns = {c["name"] for c in inspector.get_columns("products")}
        if "category_attribute_values" not in columns:
            op.add_column(
                "products",
                sa.Column(
                    "category_attribute_values",
                    sa.JSON(),
                    nullable=False,
                    server_default="[]",
                ),
            )
