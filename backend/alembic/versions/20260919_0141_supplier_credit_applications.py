"""Where a return's supplier credit was set against a bill (D-FIN-19).

A completed purchase return debits accounts payable with its whole total. One
raised from the supplier's bill takes that off the bill (D-BUY-6); one raised
from the goods receipt names no bill, so the debit stood in payables with
nothing on the purchasing side tracking it per supplier -- the payment screen
still offered the whole bill, and the supplier could be deleted with the credit
belonging to nobody.

What such a return leaves on the supplier's account is derived from the
return itself; ``supplier_credit_applications`` records only where it was set
against a bill, which nothing else can say. Applying posts no journal, as
applying a customer's advance posts none.

Idempotent: the table is created only where ``purchase_returns`` exists (the
platform schema holds no firm data once pruned) and the table does not already
exist (firm stores are partly built by ``create_all``). The table is
firm-owned, so run this through ``scripts/migrate_all_stores.py``.

Revision ID: 20260919_0141
Revises: 20260919_0140
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0141"
down_revision: str | Sequence[str] | None = "20260919_0140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "supplier_credit_applications"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP` because a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails.
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    """Create the table where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("purchase_returns") or inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("purchase_return_id", UUIDType(), nullable=False),
        sa.Column("purchase_invoice_id", UUIDType(), nullable=False),
        sa.Column("applied_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint(
            "amount > 0", name="CK_supplier_credit_applications_positive"
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name="FK_supplier_credit_applications_vendor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_return_id"],
            ["purchase_returns.id"],
            name="FK_supplier_credit_applications_purchase_return_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_invoice_id"],
            ["purchase_invoices.id"],
            name="FK_supplier_credit_applications_purchase_invoice_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_supplier_credit_applications_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_supplier_credit_applications_return",
        _TABLE,
        ["firm_id", "purchase_return_id"],
    )
    op.create_index(
        "IX_supplier_credit_applications_invoice",
        _TABLE,
        ["firm_id", "purchase_invoice_id"],
    )
    op.create_index(
        "IX_supplier_credit_applications_vendor", _TABLE, ["firm_id", "vendor_id"]
    )


def downgrade() -> None:
    """Drop the table, forgetting which bills supplier credit was set against."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
