"""Enquiries and leads (SEL-10, decision A133).

* ``enquiries``: who asked, what it is worth, the next follow-up, the status.
* ``enquiry_lines``: what was asked for.
* ``enquiry_follow_ups``: each contact.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0295
Revises: 20261003_0294
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0295"
down_revision: str | Sequence[str] | None = "20261003_0294"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
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
    ]


def upgrade() -> None:
    """Create the three tables where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    # Every table these refer to must be in the store: the platform store
    # holds some document tables but not the masters.
    for needed in ("sales_quotations", "customers", "products", "branches"):
        if not inspector.has_table(needed):
            return
    if not inspector.has_table("enquiries"):
        op.create_table(
            "enquiries",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("enquiry_number", sa.String(60), nullable=False),
            sa.Column("enquiry_date", sa.Date(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("customer_id", UUIDType(), nullable=True),
            sa.Column("prospect_name", sa.String(200), nullable=True),
            sa.Column("prospect_company", sa.String(200), nullable=True),
            sa.Column("prospect_phone", sa.String(20), nullable=True),
            sa.Column("prospect_email", sa.String(320), nullable=True),
            sa.Column("prospect_city", sa.String(100), nullable=True),
            sa.Column(
                "source",
                sa.String(20),
                server_default=sa.text("'OTHER'"),
                nullable=False,
            ),
            sa.Column("salesman_id", UUIDType(), nullable=True),
            sa.Column(
                "expected_value",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column("expected_close_on", sa.Date(), nullable=True),
            sa.Column("next_follow_up_on", sa.Date(), nullable=True),
            sa.Column(
                "status", sa.String(20), server_default=sa.text("'OPEN'"), nullable=False
            ),
            sa.Column("lost_reason", sa.String(40), nullable=True),
            sa.Column("lost_remarks", sa.Text(), nullable=True),
            sa.Column("quotation_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_enquiries"),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="FK_enquiries_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
                name="FK_enquiries_customer_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["quotation_id"],
                ["sales_quotations.id"],
                name="FK_enquiries_quotation_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index("IX_enquiries_firm_id", "enquiries", ["firm_id"])
        op.create_index("IX_enquiries_firm_status", "enquiries", ["firm_id", "status"])
        op.create_index(
            "IX_enquiries_firm_follow_up",
            "enquiries",
            ["firm_id", "next_follow_up_on"],
        )
        op.create_index(
            "UQ_enquiries_number_active",
            "enquiries",
            ["firm_id", "enquiry_number"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("enquiry_lines"):
        op.create_table(
            "enquiry_lines",
            *_base_columns(),
            sa.Column("enquiry_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=True),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column("expected_price", sa.Numeric(18, 4), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_enquiry_lines"),
            sa.ForeignKeyConstraint(
                ["enquiry_id"],
                ["enquiries.id"],
                name="FK_enquiry_lines_enquiry_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_enquiry_lines_product_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_enquiry_lines_firm_id", "enquiry_lines", ["firm_id"])
        op.create_index("IX_enquiry_lines_enquiry", "enquiry_lines", ["enquiry_id"])
    if not inspector.has_table("enquiry_follow_ups"):
        op.create_table(
            "enquiry_follow_ups",
            *_base_columns(),
            sa.Column("enquiry_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("followed_on", sa.Date(), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("next_follow_up_on", sa.Date(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_enquiry_follow_ups"),
            sa.ForeignKeyConstraint(
                ["enquiry_id"],
                ["enquiries.id"],
                name="FK_enquiry_follow_ups_enquiry_id",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "IX_enquiry_follow_ups_firm_id", "enquiry_follow_ups", ["firm_id"]
        )
        op.create_index(
            "IX_enquiry_follow_ups_enquiry", "enquiry_follow_ups", ["enquiry_id"]
        )


def downgrade() -> None:
    """Drop the three tables."""
    inspector = sa.inspect(op.get_bind())
    for table in ("enquiry_follow_ups", "enquiry_lines", "enquiries"):
        if inspector.has_table(table):
            op.drop_table(table)
