"""What a purchase return comes back as, and supplier refunds (69 row 7).

* ``purchase_returns.outcome``: ``CREDIT`` (every return already written, which
  is what each of them gave), ``REPLACEMENT`` or ``REFUND``.
* ``supplier_credit_refunds``: money a supplier paid back against one return's
  credit, with the journal that posted it and the one that reversed it.

No permission codes: receiving a supplier's refund takes the same codes as
recording a payment to them.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0209
Revises: 20261002_0208
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0209"
down_revision: str | Sequence[str] | None = "20261002_0208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "supplier_credit_refunds"


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
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
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _fk(column: str, table: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named by its referring column, as the ORM does."""
    return sa.ForeignKeyConstraint(
        [column], [f"{table}.id"], name=f"FK_{_TABLE}_{column}", ondelete="RESTRICT"
    )


def upgrade() -> None:
    """Add the column and the table where this store holds their parents."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("purchase_returns"):
        return
    if not any(
        column["name"] == "outcome"
        for column in inspector.get_columns("purchase_returns")
    ):
        op.add_column(
            "purchase_returns",
            sa.Column(
                "outcome", sa.String(length=20), nullable=False, server_default="CREDIT"
            ),
        )
    if inspector.has_table(_TABLE) or not inspector.has_table("journal_entries"):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("purchase_return_id", UUIDType(), nullable=False),
        sa.Column("refunded_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("ledger_account_id", UUIDType(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("amount > 0", name="CK_supplier_credit_refunds_positive"),
        _fk("vendor_id", "vendors"),
        _fk("purchase_return_id", "purchase_returns"),
        _fk("ledger_account_id", "ledger_accounts"),
        _fk("journal_entry_id", "journal_entries"),
        _fk("reversal_journal_entry_id", "journal_entries"),
    )
    op.create_index("IX_supplier_credit_refunds_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_supplier_credit_refunds_return", _TABLE, ["firm_id", "purchase_return_id"]
    )
    op.create_index(
        "IX_supplier_credit_refunds_vendor", _TABLE, ["firm_id", "vendor_id"]
    )


def downgrade() -> None:
    """Drop the table and the column where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("purchase_returns") and any(
        column["name"] == "outcome"
        for column in inspector.get_columns("purchase_returns")
    ):
        op.drop_column("purchase_returns", "outcome")
