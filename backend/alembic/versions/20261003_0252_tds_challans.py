"""TDS challans and a supplier's usual TDS section (ACC-7, decision A79).

* ``tds_challans`` -- one deposit of TDS under one section: BSR code, date
  deposited and challan serial (the CIN), the tax, interest and late fee, the
  bank it left and the journal it posted. One live challan per CIN.
* ``tds_challan_items`` -- the deductions (a payment's or an expense's) it
  paid; a deduction sits on one live challan only, held by a partial key.
* ``vendors.default_tds_section`` -- the section a payment to the supplier is
  usually deducted under; the payment screen fills it in.
* The control purpose ``TDS_INTEREST_AND_FEES`` on *Interest and Fees on TDS*
  (6930, an indirect expense) for every firm whose books are open, only where
  missing and never overwriting -- the shape of ``20261003_0243``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0252
Revises: 20261003_0251
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0252"
down_revision: str | Sequence[str] | None = "20261003_0251"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE = "TDS_INTEREST_AND_FEES"
_ACCOUNT = ("6930", "Interest and Fees on TDS", "EXPENSE", "IEXP", "Indirect Expenses")


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries."""
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
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _create_challans(inspector: sa.Inspector) -> None:
    """Create the challan table where it is missing."""
    if inspector.has_table("tds_challans"):
        return
    op.create_table(
        "tds_challans",
        *_base_columns(),
        sa.Column("challan_number", sa.String(60), nullable=False),
        sa.Column("deposited_on", sa.Date(), nullable=False),
        sa.Column("bsr_code", sa.String(7), nullable=False),
        sa.Column("challan_serial", sa.String(5), nullable=False),
        sa.Column("section", sa.String(10), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "interest_amount",
            sa.Numeric(18, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "fee_amount", sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("paid_from_account_id", UUIDType(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'POSTED'"), nullable=False
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=False),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_tds_challans"),
        sa.UniqueConstraint("firm_id", "challan_number", name="UQ_tds_challans_number"),
        sa.CheckConstraint("tax_amount > 0", name="CK_tds_challans_tax_positive"),
        sa.CheckConstraint(
            "interest_amount >= 0 AND fee_amount >= 0",
            name="CK_tds_challans_charges_not_negative",
        ),
        sa.ForeignKeyConstraint(
            ["paid_from_account_id"],
            ["ledger_accounts.id"],
            name="FK_tds_challans_paid_from_account_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="FK_tds_challans_journal_entry_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_journal_entry_id"],
            ["journal_entries.id"],
            name="FK_tds_challans_reversal_journal_entry_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_tds_challans_firm_id", "tds_challans", ["firm_id"])
    op.create_index(
        "IX_tds_challans_firm_date", "tds_challans", ["firm_id", "deposited_on"]
    )
    op.create_index(
        "UQ_tds_challans_cin_live",
        "tds_challans",
        ["firm_id", "bsr_code", "deposited_on", "challan_serial"],
        unique=True,
        postgresql_where=sa.text("status = 'POSTED' AND is_deleted = false"),
        sqlite_where=sa.text("status = 'POSTED' AND is_deleted = 0"),
    )


def _create_items(inspector: sa.Inspector) -> None:
    """Create the challan item table where it is missing."""
    if inspector.has_table("tds_challan_items"):
        return
    op.create_table(
        "tds_challan_items",
        *_base_columns(),
        sa.Column("challan_id", UUIDType(), nullable=False),
        sa.Column("settlement_id", UUIDType(), nullable=True),
        sa.Column("expense_id", UUIDType(), nullable=True),
        sa.Column("tds_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "is_live", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_tds_challan_items"),
        sa.CheckConstraint(
            "(settlement_id IS NULL) <> (expense_id IS NULL)",
            name="CK_tds_challan_items_one_source",
        ),
        sa.CheckConstraint("tds_amount > 0", name="CK_tds_challan_items_positive"),
        sa.ForeignKeyConstraint(
            ["challan_id"],
            ["tds_challans.id"],
            name="FK_tds_challan_items_challan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name="FK_tds_challan_items_settlement_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["expenses.id"],
            name="FK_tds_challan_items_expense_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_tds_challan_items_firm_id", "tds_challan_items", ["firm_id"])
    op.create_index(
        "IX_tds_challan_items_challan_id", "tds_challan_items", ["challan_id"]
    )
    op.create_index(
        "UQ_tds_challan_items_settlement_live",
        "tds_challan_items",
        ["settlement_id"],
        unique=True,
        postgresql_where=sa.text("is_live = true AND settlement_id IS NOT NULL"),
        sqlite_where=sa.text("is_live = 1 AND settlement_id IS NOT NULL"),
    )
    op.create_index(
        "UQ_tds_challan_items_expense_live",
        "tds_challan_items",
        ["expense_id"],
        unique=True,
        postgresql_where=sa.text("is_live = true AND expense_id IS NOT NULL"),
        sqlite_where=sa.text("is_live = 1 AND expense_id IS NOT NULL"),
    )


def _group_for(bind: sa.Connection, firm_id: object) -> object:
    """Return the firm's indirect-expense group, creating it only if missing."""
    _, _, kind, code, name = _ACCOUNT
    group_id = bind.execute(
        sa.text(
            "SELECT id FROM account_groups WHERE firm_id = :firm "
            "AND code = :code AND is_deleted = false"
        ),
        {"firm": firm_id, "code": code},
    ).scalar()
    if group_id is not None:
        return group_id
    group_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO account_groups (id, firm_id, code, name, "
            "account_type, is_active, is_deleted, version, "
            "created_at, updated_at) VALUES (:id, :firm, :code, "
            ":name, :kind, true, false, 1, now(), now())"
        ),
        {"id": group_id, "firm": firm_id, "code": code, "name": name, "kind": kind},
    )
    return group_id


def _seed_purpose(inspector: sa.Inspector) -> None:
    """Map the interest-and-fees purpose for every firm whose books are open."""
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "firm_control_accounts"
    ):
        return
    bind = op.get_bind()
    code, name, kind, _, _ = _ACCOUNT
    firms = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT firm_id FROM ledger_accounts WHERE is_deleted = false"
            )
        )
        .scalars()
        .all()
    )
    for firm_id in firms:
        mapped = bind.execute(
            sa.text(
                "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                "AND purpose = :purpose AND is_deleted = false"
            ),
            {"firm": firm_id, "purpose": _PURPOSE},
        ).scalar()
        if mapped is not None:
            continue
        found = bind.execute(
            sa.text(
                "SELECT id, account_type FROM ledger_accounts "
                "WHERE firm_id = :firm AND code = :code AND is_deleted = false"
            ),
            {"firm": firm_id, "code": code},
        ).first()
        if found is not None and found[1] != kind:
            # The firm used the code for something else. Left for the firm.
            continue
        account_id = None if found is None else found[0]
        if account_id is None:
            account_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO ledger_accounts (id, firm_id, "
                    "account_group_id, code, name, account_type, "
                    "is_balance_sheet, is_profit_loss, "
                    "requires_cost_center, requires_profit_center, "
                    "is_active, is_deleted, version, created_at, "
                    "updated_at) VALUES (:id, :firm, :group, :code, :name, "
                    ":kind, false, true, false, false, "
                    "true, false, 1, now(), now())"
                ),
                {
                    "id": account_id,
                    "firm": firm_id,
                    "group": _group_for(bind, firm_id),
                    "code": code,
                    "name": name,
                    "kind": kind,
                },
            )
        bind.execute(
            sa.text(
                "INSERT INTO firm_control_accounts (id, firm_id, purpose, "
                "ledger_account_id, is_deleted, version, created_at, "
                "updated_at) VALUES (:id, :firm, :purpose, :account, "
                "false, 1, now(), now())"
            ),
            {
                "id": uuid4(),
                "firm": firm_id,
                "purpose": _PURPOSE,
                "account": account_id,
            },
        )


def upgrade() -> None:
    """Build the challan tables, the supplier column and the purpose."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("vendors"):
        return
    columns = {column["name"] for column in inspector.get_columns("vendors")}
    if "default_tds_section" not in columns:
        op.add_column(
            "vendors", sa.Column("default_tds_section", sa.String(10), nullable=True)
        )
    if inspector.has_table("settlements") and inspector.has_table("expenses"):
        _create_challans(inspector)
        _create_items(inspector)
    _seed_purpose(inspector)


def downgrade() -> None:
    """Drop the tables, the column and the mapping; keep the account."""
    inspector = sa.inspect(op.get_bind())
    for table in ("tds_challan_items", "tds_challans"):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("vendors") and "default_tds_section" in {
        column["name"] for column in inspector.get_columns("vendors")
    }:
        op.drop_column("vendors", "default_tds_section")
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'TDS_INTEREST_AND_FEES'"
            )
        )
