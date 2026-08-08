"""Finance general-ledger foundation.

Creates the accounting calendar, the chart of accounts, the double-entry
journal, and the derived balance and receivable/payable ledger tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0042"
down_revision: str | Sequence[str] | None = "20260808_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "vendor_ledgers",
    "customer_ledgers",
    "gl_postings",
    "ledger_balances",
    "journal_lines",
    "journal_entries",
    "voucher_types",
    "journal_types",
    "profit_centers",
    "cost_centers",
    "ledger_accounts",
    "account_groups",
    "accounting_periods",
    "financial_years",
)


def _base_columns() -> list[sa.Column[object]]:
    """Return the shared BaseEntity columns used by every finance table."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    ]


def _money(name: str) -> sa.Column[object]:
    """Return a non-null two-decimal money column defaulting to zero."""
    return sa.Column(name, sa.Numeric(18, 2), nullable=False, server_default="0")


def _external_fk(
    present: set[str], columns: list[str], target: str, **kwargs: object
) -> list[sa.ForeignKeyConstraint]:
    """Return a foreign key only when its target table lives in this schema.

    Finance tables are firm-owned, so they are created both in the platform
    schema and in each firm schema. ``firms`` lives only in the platform schema
    while ``customers`` and ``vendors`` live only in firm schemas, so neither
    reference can be declared unconditionally. Existing firm-owned tables follow
    the same rule: no firm-owned table in ``firm_shared`` carries a ``firm_id``
    foreign key.
    """
    table = target.split(".", 1)[0]
    if table not in present:
        return []
    return [sa.ForeignKeyConstraint(columns, [target], **kwargs)]  # type: ignore[arg-type]


def upgrade() -> None:
    """Create the finance schema."""
    inspector = sa.inspect(op.get_bind())
    present = {
        name for name in ("firms", "customers", "vendors") if inspector.has_table(name)
    }
    op.create_table(
        "financial_years",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.UniqueConstraint("firm_id", "code", name="UQ_financial_years_firm_code"),
    )
    op.create_index("IX_financial_years_firm_id", "financial_years", ["firm_id"])
    op.create_index(
        "IX_financial_years_firm_active", "financial_years", ["firm_id", "is_active"]
    )

    op.create_table(
        "accounting_periods",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("financial_year_id", sa.Uuid(), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="OPEN"
        ),
        sa.Column("description", sa.Text(), nullable=True),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "financial_year_id",
            "period_number",
            name="UQ_accounting_periods_year_number",
        ),
        sa.UniqueConstraint("firm_id", "code", name="UQ_accounting_periods_firm_code"),
    )
    op.create_index("IX_accounting_periods_firm_id", "accounting_periods", ["firm_id"])
    op.create_index(
        "IX_accounting_periods_financial_year_id",
        "accounting_periods",
        ["financial_year_id"],
    )
    op.create_index(
        "IX_accounting_periods_firm_status", "accounting_periods", ["firm_id", "status"]
    )

    op.create_table(
        "account_groups",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("parent_group_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["parent_group_id"], ["account_groups.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("firm_id", "code", name="UQ_account_groups_firm_code"),
    )
    op.create_index("IX_account_groups_firm_id", "account_groups", ["firm_id"])
    op.create_index(
        "IX_account_groups_firm_type", "account_groups", ["firm_id", "account_type"]
    )

    op.create_table(
        "ledger_accounts",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("account_group_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_balance_sheet",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_profit_loss",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "requires_cost_center",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "requires_profit_center",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["account_group_id"], ["account_groups.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("firm_id", "code", name="UQ_ledger_accounts_firm_code"),
    )
    op.create_index("IX_ledger_accounts_firm_id", "ledger_accounts", ["firm_id"])
    op.create_index(
        "IX_ledger_accounts_account_group_id", "ledger_accounts", ["account_group_id"]
    )
    op.create_index(
        "IX_ledger_accounts_firm_type", "ledger_accounts", ["firm_id", "account_type"]
    )
    op.create_index(
        "IX_ledger_accounts_firm_active", "ledger_accounts", ["firm_id", "is_active"]
    )

    for table in ("cost_centers", "profit_centers"):
        op.create_table(
            table,
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            *_external_fk(present, ["firm_id"], "firms.id"),
            sa.UniqueConstraint("firm_id", "code", name=f"UQ_{table}_firm_code"),
        )
        op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
        op.create_index(f"IX_{table}_firm_active", table, ["firm_id", "is_active"])

    for table in ("journal_types", "voucher_types"):
        op.create_table(
            table,
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            *_external_fk(present, ["firm_id"], "firms.id"),
            sa.UniqueConstraint("firm_id", "code", name=f"UQ_{table}_firm_code"),
        )
        op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])

    op.create_table(
        "journal_entries",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("journal_type_id", sa.Uuid(), nullable=False),
        sa.Column("voucher_type_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("journal_date", sa.Date(), nullable=False),
        sa.Column("reference_number", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        _money("total_debit"),
        _money("total_credit"),
        sa.Column(
            "is_balanced", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("source_module", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["journal_type_id"], ["journal_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["voucher_type_id"], ["voucher_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["accounting_period_id"], ["accounting_periods.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["journal_entries.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "firm_id", "reference_number", name="UQ_journal_entries_firm_reference"
        ),
    )
    op.create_index("IX_journal_entries_firm_id", "journal_entries", ["firm_id"])
    op.create_index(
        "IX_journal_entries_firm_status", "journal_entries", ["firm_id", "status"]
    )
    op.create_index(
        "IX_journal_entries_firm_period",
        "journal_entries",
        ["firm_id", "accounting_period_id"],
    )
    op.create_index(
        "IX_journal_entries_source", "journal_entries", ["source_module", "source_id"]
    )

    op.create_table(
        "journal_lines",
        *_base_columns(),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("profit_center_id", sa.Uuid(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        _money("debit_amount"),
        _money("credit_amount"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cost_center_id"], ["cost_centers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["profit_center_id"], ["profit_centers.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "journal_entry_id", "line_number", name="UQ_journal_lines_entry_line"
        ),
    )
    op.create_index(
        "IX_journal_lines_journal_entry_id", "journal_lines", ["journal_entry_id"]
    )
    op.create_index("IX_journal_lines_account", "journal_lines", ["ledger_account_id"])

    op.create_table(
        "ledger_balances",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        _money("opening_balance"),
        _money("period_debit"),
        _money("period_credit"),
        _money("closing_balance"),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["accounting_period_id"], ["accounting_periods.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "ledger_account_id",
            "accounting_period_id",
            name="UQ_ledger_balances_account_period",
        ),
    )
    op.create_index("IX_ledger_balances_firm_id", "ledger_balances", ["firm_id"])
    op.create_index(
        "IX_ledger_balances_firm_period",
        "ledger_balances",
        ["firm_id", "accounting_period_id"],
    )

    op.create_table(
        "gl_postings",
        *_base_columns(),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("journal_line_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("posting_date", sa.DateTime(timezone=True), nullable=False),
        _money("debit_amount"),
        _money("credit_amount"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="POSTED"
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("posted_by", sa.Uuid(), nullable=False),
        *_external_fk(present, ["firm_id"], "firms.id"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["journal_line_id"], ["journal_lines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["accounting_period_id"], ["accounting_periods.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("IX_gl_postings_firm_id", "gl_postings", ["firm_id"])
    op.create_index(
        "IX_gl_postings_firm_period", "gl_postings", ["firm_id", "accounting_period_id"]
    )
    op.create_index(
        "IX_gl_postings_account",
        "gl_postings",
        ["ledger_account_id", "accounting_period_id"],
    )

    for table, party, party_table in (
        ("customer_ledgers", "customer_id", "customers"),
        ("vendor_ledgers", "vendor_id", "vendors"),
    ):
        entity = table.removesuffix("_ledgers")
        op.create_table(
            table,
            *_base_columns(),
            sa.Column("firm_id", sa.Uuid(), nullable=False),
            sa.Column(party, sa.Uuid(), nullable=False),
            sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
            _money("invoice_amount"),
            _money("payment_amount"),
            _money("outstanding_amount"),
            sa.Column(
                "days_overdue",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            *_external_fk(present, ["firm_id"], "firms.id"),
            *_external_fk(present, [party], f"{party_table}.id", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["accounting_period_id"], ["accounting_periods.id"], ondelete="RESTRICT"
            ),
            sa.UniqueConstraint(
                "firm_id",
                party,
                "accounting_period_id",
                name=f"UQ_{table}_firm_{entity}_period",
            ),
        )
        op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
        op.create_index(f"IX_{table}_{party}", table, [party])


def downgrade() -> None:
    """Drop the finance schema in dependency-safe order."""
    for table in _TABLES:
        op.drop_table(table)
