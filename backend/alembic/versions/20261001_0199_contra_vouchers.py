"""Contra vouchers: money moved between the firm's own accounts (74 row 3).

* ``contra_vouchers``: a deposit, withdrawal, bank-to-bank or cash-to-cash
  transfer, with the journal it posted and the mirror that cancelled it.

No permission codes: a contra is read, recorded and cancelled under the
existing ``JOURNAL_VIEW`` / ``JOURNAL_POST`` / ``JOURNAL_REVERSE``, so no grant
needs reconciling. No control purpose either: it posts between accounts the
firm already nominated (CASH, BANK) and the accounts grouped with them.

Idempotent; firm-owned, so it runs per store (``scripts/migrate_all_stores.py``)
and creates the table only in a store that holds the ledger. Cross-schema
foreign keys are declared only where the target exists in the store.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0199"
down_revision: str | Sequence[str] | None = "20261001_0198"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "contra_vouchers"


def _external_fk(
    inspector: sa.Inspector, table: str, column: str, name: str
) -> list[sa.ForeignKeyConstraint]:
    """Declare a foreign key only where its target actually exists."""
    if not inspector.has_table(table):
        return []
    return [
        sa.ForeignKeyConstraint(
            [column], [f"{table}.id"], name=name, ondelete="RESTRICT"
        )
    ]


def _base_columns() -> list[sa.Column]:
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
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def upgrade() -> None:
    """Create the contra voucher table where a ledger store lacks it."""
    inspector = sa.inspect(op.get_bind())
    # A store that holds the ledger is one a voucher can post into.
    if not inspector.has_table("journal_entries") or inspector.has_table(_TABLE):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    for table, column in (
        ("ledger_accounts", "from_account_id"),
        ("ledger_accounts", "to_account_id"),
        ("journal_entries", "journal_entry_id"),
        ("journal_entries", "reversal_journal_entry_id"),
    ):
        constraints += _external_fk(
            inspector, table, column, f"FK_contra_vouchers_{column}"
        )
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("voucher_number", sa.String(length=60), nullable=False),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("from_account_id", UUIDType(), nullable=False),
        sa.Column("to_account_id", UUIDType(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_contra_vouchers"),
        sa.UniqueConstraint(
            "firm_id", "voucher_number", name="UQ_contra_vouchers_number"
        ),
        sa.CheckConstraint("amount > 0", name="CK_contra_vouchers_amount_positive"),
        sa.CheckConstraint(
            "from_account_id <> to_account_id",
            name="CK_contra_vouchers_distinct_accounts",
        ),
        *constraints,
    )
    op.create_index("IX_contra_vouchers_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_contra_vouchers_firm_date", _TABLE, ["firm_id", "voucher_date"])
    op.create_index("IX_contra_vouchers_firm_status", _TABLE, ["firm_id", "status"])


def downgrade() -> None:
    """Drop the table. The journals it posted stay; they are the ledger's."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
