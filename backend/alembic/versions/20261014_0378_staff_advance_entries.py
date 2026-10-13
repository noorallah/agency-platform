"""Staff advances: an advance to an employee and its recovery (backlog 153, P4).

One table, ``staff_advance_entries``: which employee, which way (an advance or
a recovery), how much, the account on the other side, and the journal that
recorded it. An employee is a ledger account in the *Staff Advances* group
(``CA-STAFF``), which the service opens with the first employee, so nothing is
seeded here. What an employee owes is the balance of his account and is
stored nowhere.

No permission codes: the screen is gated on the expense codes the firm's
roles already hold.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where it is missing, and only in a store that has a ledger.
``firms`` exists only in the platform schema, so the ``firm_id`` key is
declared only where it does.

Revision ID: 20261014_0378
Revises: 20261014_0377
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0378"
down_revision: str | Sequence[str] | None = "20261014_0377"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "staff_advance_entries"


def _external_fk(
    inspector: sa.Inspector, table: str, column: str, name: str
) -> list[sa.ForeignKeyConstraint]:
    """Declare a foreign key only where its target actually exists."""
    if not inspector.has_table(table):
        return []
    return [sa.ForeignKeyConstraint([column], [f"{table}.id"], name=name)]


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
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
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _ledger_fk(column: str, target: str) -> sa.ForeignKeyConstraint:
    """Return a RESTRICT key from one of this table's columns to the ledger."""
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=f"FK_{_TABLE}_{column}",
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    """Create the staff advance entries table where a firm store lacks it."""
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
        sa.Column("entry_number", sa.String(length=60), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("employee_account_id", UUIDType(), nullable=False),
        sa.Column("other_account_id", UUIDType(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.UniqueConstraint(
            "firm_id", "entry_number", name="UQ_staff_advance_entries_firm_number"
        ),
        sa.CheckConstraint(
            "amount > 0", name="CK_staff_advance_entries_amount_positive"
        ),
        _ledger_fk("employee_account_id", "ledger_accounts"),
        _ledger_fk("other_account_id", "ledger_accounts"),
        _ledger_fk("journal_entry_id", "journal_entries"),
        _ledger_fk("reversal_journal_entry_id", "journal_entries"),
        *_external_fk(inspector, "firms", "firm_id", f"FK_{_TABLE}_firm_id"),
    )
    op.create_index("IX_staff_advance_entries_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_staff_advance_entries_firm_date", _TABLE, ["firm_id", "entry_date"]
    )
    op.create_index(
        "IX_staff_advance_entries_firm_employee",
        _TABLE,
        ["firm_id", "employee_account_id"],
    )


def downgrade() -> None:
    """Drop the table. The employees' accounts are the ledger's and stay."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
