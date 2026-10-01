"""One month's GST settled: set-off, cash paid, credit carried (backlog 63).

``gst_payments``: the month's liability, credit available, credit used,
cash paid and credit carried forward, head by head (IGST, CGST, SGST, cess),
the challan's CPIN and CIN, interest and late fee with the expense accounts
they went to, and the journal that posted it. One standing settlement per
firm per month, held by a partial unique index.

No permission codes: recording a challan takes ``JOURNAL_POST``, reading
takes ``ACCOUNT_VIEW`` or ``SALES_VIEW``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261001_0176
Revises: 20261001_0175
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0176"
down_revision: str | Sequence[str] | None = "20261001_0175"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "gst_payments"
_HEADS = ("igst", "cgst", "sgst", "cess")
_MONEY = ("liability", "credit", "used", "cash", "carried")


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


def _money(name: str) -> sa.Column:  # type: ignore[type-arg]
    """Return a money column defaulting to zero."""
    return sa.Column(name, sa.Numeric(18, 2), nullable=False, server_default="0")


def _fk(column: str, table: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named by its referring column, as the ORM does."""
    return sa.ForeignKeyConstraint(
        [column], [f"{table}.id"], name=f"FK_{_TABLE}_{column}", ondelete="RESTRICT"
    )


def upgrade() -> None:
    """Create the table where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    # A store without a ledger is not a firm store; it has nothing to post to.
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "journal_entries"
    ):
        return
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("return_period", sa.String(length=7), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("money_account_id", UUIDType(), nullable=False),
        sa.Column("challan_cpin", sa.String(length=20), nullable=True),
        sa.Column("challan_cin", sa.String(length=30), nullable=True),
        *[_money(f"{kind}_{head}") for kind in _MONEY for head in _HEADS],
        _money("interest_amount"),
        sa.Column("interest_account_id", UUIDType(), nullable=True),
        _money("late_fee_amount"),
        sa.Column("late_fee_account_id", UUIDType(), nullable=True),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", UUIDType(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        _fk("money_account_id", "ledger_accounts"),
        _fk("interest_account_id", "ledger_accounts"),
        _fk("late_fee_account_id", "ledger_accounts"),
        _fk("journal_entry_id", "journal_entries"),
        _fk("reversal_journal_entry_id", "journal_entries"),
    )
    op.create_index("IX_gst_payments_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_gst_payments_firm_period", _TABLE, ["firm_id", "return_period"])
    op.create_index(
        "UQ_gst_payments_firm_period_posted",
        _TABLE,
        ["firm_id", "return_period"],
        unique=True,
        postgresql_where=sa.text("status = 'POSTED' AND is_deleted = false"),
        sqlite_where=sa.text("status = 'POSTED' AND is_deleted = 0"),
    )


def downgrade() -> None:
    """Drop the table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
