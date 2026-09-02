"""Coupons, usage limits, and the ledger that counts them.

A coupon is a way of *reaching* an offer, not a second kind of one: the
benefit, the conditions and the stacking rule all still live on the promotion
it names. What a coupon adds is that the offer applies only when somebody asks
for it by name.

`promotion_redemptions` is the ledger a limit is counted from. Not a counter on
the promotion: a counter would have to be written while a document is priced,
and pricing must never commit, so it would either publish a half-written order
or count a draft that is edited five more times and never approved. The ledger
records a claim as PENDING when the document is priced, CLAIMED when it is
approved, and REVERSED when it is cancelled -- and only a claim counts.

`sales_orders.coupon_code` is on the order rather than the quotation because
the order is the document that is approved, and approval is when a claim can be
counted. An offer is not a claim.

Firm-owned throughout, so `firm_id` carries no foreign key and the platform
schema gets nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260903_0108"
down_revision: str | Sequence[str] | None = "20260903_0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """Return the `BaseEntity` columns every table here carries."""
    return [
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
    ]


def upgrade() -> None:
    """Add coupons, the redemption ledger, and the limits they enforce."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: the platform schema holds no promotions to couple to.
    if not inspector.has_table("promotions"):
        return

    columns = {column["name"] for column in inspector.get_columns("promotions")}
    if "requires_coupon" not in columns:
        op.add_column(
            "promotions",
            sa.Column(
                "requires_coupon",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    for name in ("max_redemptions", "max_redemptions_per_customer"):
        if name not in columns:
            # Nullable on purpose: no limit and a limit of zero are different
            # answers, and a default would invent one nobody chose.
            op.add_column("promotions", sa.Column(name, sa.Integer(), nullable=True))

    if inspector.has_table("sales_orders"):
        order_columns = {
            column["name"] for column in inspector.get_columns("sales_orders")
        }
        if "coupon_code" not in order_columns:
            op.add_column(
                "sales_orders",
                sa.Column("coupon_code", sa.String(length=40), nullable=True),
            )

    if not inspector.has_table("promotion_coupons"):
        op.create_table(
            "promotion_coupons",
            *_base_columns(),
            sa.Column("promotion_id", UUIDType(), nullable=False),
            sa.Column("code", sa.String(length=40), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "status", sa.String(length=20), server_default="ACTIVE", nullable=False
            ),
            sa.Column("max_redemptions", sa.Integer(), nullable=True),
            sa.Column("max_redemptions_per_customer", sa.Integer(), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_promotion_coupons"),
            sa.UniqueConstraint(
                "firm_id", "code", name="UQ_promotion_coupons_firm_code"
            ),
            sa.ForeignKeyConstraint(
                ["promotion_id"],
                ["promotions.id"],
                name="FK_promotion_coupons_promotion_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "IX_promotion_coupons_firm_id", "promotion_coupons", ["firm_id"]
        )
        op.create_index(
            "IX_promotion_coupons_promotion_id", "promotion_coupons", ["promotion_id"]
        )
        op.create_index(
            "IX_promotion_coupons_firm_promotion",
            "promotion_coupons",
            ["firm_id", "promotion_id"],
        )

    if not inspector.has_table("promotion_redemptions"):
        op.create_table(
            "promotion_redemptions",
            *_base_columns(),
            sa.Column("promotion_id", UUIDType(), nullable=False),
            sa.Column("coupon_id", UUIDType(), nullable=True),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("document_type", sa.String(length=40), nullable=False),
            sa.Column("document_id", UUIDType(), nullable=False),
            sa.Column("document_number", sa.String(length=60), nullable=True),
            sa.Column("redeemed_on", sa.Date(), nullable=False),
            sa.Column(
                "benefit_amount",
                sa.Numeric(18, 4),
                server_default="0",
                nullable=False,
            ),
            sa.Column(
                "status", sa.String(length=20), server_default="CLAIMED", nullable=False
            ),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_promotion_redemptions"),
            sa.ForeignKeyConstraint(
                ["promotion_id"],
                ["promotions.id"],
                name="FK_promotion_redemptions_promotion_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["coupon_id"],
                ["promotion_coupons.id"],
                name="FK_promotion_redemptions_coupon_id",
                ondelete="RESTRICT",
            ),
        )
        for name, cols in (
            ("IX_promotion_redemptions_firm_id", ["firm_id"]),
            ("IX_promotion_redemptions_promotion_id", ["promotion_id"]),
            ("IX_promotion_redemptions_customer_id", ["customer_id"]),
            ("IX_promotion_redemptions_firm_promotion", ["firm_id", "promotion_id"]),
            ("IX_promotion_redemptions_firm_customer", ["firm_id", "customer_id"]),
            ("IX_promotion_redemptions_document", ["firm_id", "document_id"]),
        ):
            op.create_index(name, "promotion_redemptions", cols)


def downgrade() -> None:
    """Drop the ledger, the coupons, and the columns that fed them."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("promotion_redemptions", "promotion_coupons"):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("sales_orders"):
        columns = {column["name"] for column in inspector.get_columns("sales_orders")}
        if "coupon_code" in columns:
            op.drop_column("sales_orders", "coupon_code")
    if inspector.has_table("promotions"):
        columns = {column["name"] for column in inspector.get_columns("promotions")}
        for name in (
            "max_redemptions_per_customer",
            "max_redemptions",
            "requires_coupon",
        ):
            if name in columns:
                op.drop_column("promotions", name)
