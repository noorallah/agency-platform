"""Bank statements and their reconciliation (ACC-1, decision A125).

* ``bank_statements``: one imported statement against one bank ledger account.
* ``bank_statement_lines``: its lines, each a deposit or a withdrawal.
* ``bank_reconciliation_matches``: a line accounting for a posting on the bank
  account; one live match per posting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0287
Revises: 20261003_0286
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0287"
down_revision: str | Sequence[str] | None = "20261003_0286"
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
    """Create the statement tables where a firm's ledger lives."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no ledger.
    if not inspector.has_table("gl_postings"):
        return
    if not inspector.has_table("bank_statements"):
        op.create_table(
            "bank_statements",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("ledger_account_id", UUIDType(), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("from_date", sa.Date(), nullable=False),
            sa.Column("to_date", sa.Date(), nullable=False),
            sa.Column(
                "line_count", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.PrimaryKeyConstraint("id", name="PK_bank_statements"),
            sa.ForeignKeyConstraint(
                ["ledger_account_id"],
                ["ledger_accounts.id"],
                name="FK_bank_statements_ledger_account_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_bank_statements_firm_id", "bank_statements", ["firm_id"])
        op.create_index(
            "IX_bank_statements_firm_account",
            "bank_statements",
            ["firm_id", "ledger_account_id"],
        )
    if not inspector.has_table("bank_statement_lines"):
        op.create_table(
            "bank_statement_lines",
            *_base_columns(),
            sa.Column("statement_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("ledger_account_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("line_date", sa.Date(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("reference", sa.String(120), nullable=True),
            sa.Column(
                "withdrawal",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column(
                "deposit",
                sa.Numeric(18, 2),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column("balance", sa.Numeric(18, 2), nullable=True),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'UNMATCHED'"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_bank_statement_lines"),
            sa.ForeignKeyConstraint(
                ["statement_id"],
                ["bank_statements.id"],
                name="FK_bank_statement_lines_statement_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "(withdrawal > 0 AND deposit = 0) OR (deposit > 0 AND withdrawal = 0)",
                name="CK_bank_statement_lines_one_side",
            ),
        )
        op.create_index(
            "IX_bank_statement_lines_statement",
            "bank_statement_lines",
            ["statement_id"],
        )
        op.create_index(
            "IX_bank_statement_lines_account_date",
            "bank_statement_lines",
            ["firm_id", "ledger_account_id", "line_date"],
        )
    if not inspector.has_table("bank_reconciliation_matches"):
        op.create_table(
            "bank_reconciliation_matches",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("statement_line_id", UUIDType(), nullable=False),
            sa.Column("gl_posting_id", UUIDType(), nullable=False),
            sa.Column("cleared_on", sa.Date(), nullable=False),
            sa.Column("matched_how", sa.String(10), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_bank_reconciliation_matches"),
            sa.ForeignKeyConstraint(
                ["statement_line_id"],
                ["bank_statement_lines.id"],
                name="FK_bank_reconciliation_matches_statement_line_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["gl_posting_id"],
                ["gl_postings.id"],
                name="FK_bank_reconciliation_matches_gl_posting_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "IX_bank_reconciliation_matches_firm_id",
            "bank_reconciliation_matches",
            ["firm_id"],
        )
        op.create_index(
            "IX_bank_reconciliation_matches_line",
            "bank_reconciliation_matches",
            ["statement_line_id"],
        )
        op.create_index(
            "UQ_bank_reconciliation_matches_posting_active",
            "bank_reconciliation_matches",
            ["gl_posting_id"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    """Drop the statement tables."""
    inspector = sa.inspect(op.get_bind())
    for table in (
        "bank_reconciliation_matches",
        "bank_statement_lines",
        "bank_statements",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
