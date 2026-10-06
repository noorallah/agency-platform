"""A customer's credit can be set against another bill.

``customer_credit_applications``: one row per place part of a sales return's
or credit note's credit went -- another bill of the same customer (a sales
invoice or an opening bill), or the refund that paid it back.

A completed sales return and an approved credit note credit the customer
against the bill they name. Where that bill was already paid, the excess
stood on the customer's account as an advance that belonged to no receipt,
and ``POST /receipts/{id}/allocate`` only ever spends one receipt's unapplied
money: the customer owed 826.00 on one line and was owed 826.00 on another
until somebody paid it out and took it back (D-PRC-75, PRCQ-74). What a
source has left to give is derived -- what its own bills could not absorb,
less its live rows here -- and applying posts no journal.

Nothing is backfilled. A refund recorded before this table existed named no
source; the reader takes such money off the oldest credits held on account,
because a customer cannot hold more as credit than the account says they
hold.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where missing. No ``firm_id`` foreign key (``firms`` lives only
in the platform store); the source and the target are bare ids, as a return
line names its source, and the customer is a real key because both live in
the same store.

Revision ID: 20261006_0348
Revises: 20261006_0347
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261006_0348"
down_revision: str | Sequence[str] | None = "20261006_0347"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customer_credit_applications"


def upgrade() -> None:
    """Create the table where the store holds customers and not it."""
    inspector = sa.inspect(op.get_bind())
    # A store with no customers keeps no credit of theirs: the platform
    # store, once the firm-owned tables are pruned from it.
    if not inspector.has_table("customers") or inspector.has_table(_TABLE):
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", UUIDType(), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", UUIDType(), nullable=False),
        sa.Column("applied_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "advance_amount", sa.Numeric(18, 2), server_default="0", nullable=False
        ),
        sa.Column("receivable_transaction_id", UUIDType(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="POSTED", nullable=False
        ),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", UUIDType(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_customer_credit_applications"),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="FK_customer_credit_applications_customer_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0", name="CK_customer_credit_applications_positive"
        ),
        sa.CheckConstraint(
            "source_type IN ('SALES_RETURN', 'CREDIT_NOTE')",
            name="CK_customer_credit_applications_source_type",
        ),
        sa.CheckConstraint(
            "target_type IN ('SALES_INVOICE', 'CUSTOMER_OPENING_BILL', 'REFUND')",
            name="CK_customer_credit_applications_target_type",
        ),
    )
    op.create_index(
        "IX_customer_credit_applications_source", _TABLE, ["firm_id", "source_id"]
    )
    op.create_index(
        "IX_customer_credit_applications_target", _TABLE, ["firm_id", "target_id"]
    )
    op.create_index(
        "IX_customer_credit_applications_customer", _TABLE, ["firm_id", "customer_id"]
    )


def downgrade() -> None:
    """Drop the table; a credit on a paid bill can only be refunded again."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
