"""Promises to pay, and the collector on a customer.

Backlog §87 #8 (SG-8).

* ``payment_promises``: what a customer promised to pay and by when, against a
  bill or the account as a whole. A promise is withdrawn, never edited or
  deleted, and whether it was kept is derived from the receipts.
* ``customers.collector_id``: the firm member who collects the customer's
  dues; blank leaves it to the account manager.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each object is
made only in a store that holds customers and sales invoices and lacks it.

Revision ID: 20261005_0322
Revises: 20261005_0321
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0322"
down_revision: str | Sequence[str] | None = "20261005_0321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "payment_promises"
_CUSTOMERS = "customers"
_INVOICES = "sales_invoices"


def _create_promises() -> None:
    """Create the table, with the columns every ``BaseEntity`` table carries."""
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
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=True),
        sa.Column("promised_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("recorded_by", UUIDType(), nullable=False),
        sa.Column("collector_id", UUIDType(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_payment_promises"),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="FK_payment_promises_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_invoice_id"],
            ["sales_invoices.id"],
            name="FK_payment_promises_sales_invoice_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("CK_payment_promises_amount_positive")
        ),
    )
    op.create_index(
        "IX_payment_promises_firm_promised_on", _TABLE, ["firm_id", "promised_on"]
    )
    op.create_index(
        "IX_payment_promises_firm_invoice", _TABLE, ["firm_id", "sales_invoice_id"]
    )
    op.create_index(
        "IX_payment_promises_firm_customer", _TABLE, ["firm_id", "customer_id"]
    )


def upgrade() -> None:
    """Create the table and add the customer's collector where missing."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no customers.
    if not inspector.has_table(_CUSTOMERS):
        return
    present = {column["name"] for column in inspector.get_columns(_CUSTOMERS)}
    if "collector_id" not in present:
        op.add_column(_CUSTOMERS, sa.Column("collector_id", UUIDType(), nullable=True))
    if inspector.has_table(_INVOICES) and not inspector.has_table(_TABLE):
        _create_promises()


def downgrade() -> None:
    """Drop the table and the customer's collector where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table(_CUSTOMERS):
        present = {column["name"] for column in inspector.get_columns(_CUSTOMERS)}
        if "collector_id" in present:
            op.drop_column(_CUSTOMERS, "collector_id")
