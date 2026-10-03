"""Landed cost vouchers (BUY-16, decision A129).

* ``landed_cost_vouchers``, ``landed_cost_charges`` and
  ``landed_cost_allocations``.
* ``LANDED_COST_CLEARING`` mapped to *Expenses Included in Valuation* (5210,
  direct expenses) for every firm whose books are open, the shape of
  ``20261003_0286``: only where missing, never overwriting.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0291
Revises: 20261003_0290
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0291"
down_revision: str | Sequence[str] | None = "20261003_0290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    (
        "LANDED_COST_CLEARING",
        "5210",
        "Expenses Included in Valuation",
        "EXPENSE",
        "EXP",
        "Direct Expenses",
    ),
)


def _audit_columns() -> list[sa.Column[object]]:
    """Return the columns every entity carries."""
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


def _money(name: str) -> sa.Column[object]:
    """Return an amount column defaulting to zero."""
    return sa.Column(
        name, sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
    )


def _fk(column: str, table: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named for its referring column."""
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"FK_{table}_{column}", ondelete=ondelete
    )


def _tables(inspector: sa.Inspector) -> None:
    """Create the voucher, charge and allocation tables."""
    if not inspector.has_table("landed_cost_vouchers"):
        op.create_table(
            "landed_cost_vouchers",
            *_audit_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("voucher_number", sa.String(60), nullable=False),
            sa.Column("voucher_date", sa.Date(), nullable=False),
            sa.Column("basis", sa.String(20), nullable=False),
            sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
            _money("inventory_amount"),
            _money("cogs_amount"),
            sa.Column(
                "status",
                sa.String(20),
                server_default=sa.text("'POSTED'"),
                nullable=False,
            ),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_landed_cost_vouchers"),
            _fk(
                "journal_entry_id",
                "landed_cost_vouchers",
                "journal_entries",
                "RESTRICT",
            ),
        )
        op.create_index(
            "IX_landed_cost_vouchers_firm_id", "landed_cost_vouchers", ["firm_id"]
        )
        op.create_index(
            "IX_landed_cost_vouchers_firm_date",
            "landed_cost_vouchers",
            ["firm_id", "voucher_date"],
        )
        op.create_index(
            "UQ_landed_cost_vouchers_number_active",
            "landed_cost_vouchers",
            ["firm_id", "voucher_number"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("landed_cost_charges"):
        op.create_table(
            "landed_cost_charges",
            *_audit_columns(),
            sa.Column("voucher_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("description", sa.String(200), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column("bill_reference", sa.String(100), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_landed_cost_charges"),
            _fk("voucher_id", "landed_cost_charges", "landed_cost_vouchers", "CASCADE"),
            _fk("vendor_id", "landed_cost_charges", "vendors", "RESTRICT"),
        )
        op.create_index(
            "IX_landed_cost_charges_firm_id", "landed_cost_charges", ["firm_id"]
        )
        op.create_index(
            "IX_landed_cost_charges_voucher", "landed_cost_charges", ["voucher_id"]
        )
    if not inspector.has_table("landed_cost_allocations"):
        op.create_table(
            "landed_cost_allocations",
            *_audit_columns(),
            sa.Column("voucher_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("goods_receipt_id", UUIDType(), nullable=False),
            sa.Column("goods_receipt_line_id", UUIDType(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column("basis_measure", sa.Numeric(18, 4), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("inventory_amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("cogs_amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_landed_cost_allocations"),
            _fk(
                "voucher_id",
                "landed_cost_allocations",
                "landed_cost_vouchers",
                "CASCADE",
            ),
            _fk(
                "goods_receipt_id",
                "landed_cost_allocations",
                "goods_receipts",
                "RESTRICT",
            ),
            _fk(
                "goods_receipt_line_id",
                "landed_cost_allocations",
                "goods_receipt_lines",
                "RESTRICT",
            ),
            _fk("product_id", "landed_cost_allocations", "products", "RESTRICT"),
            _fk(
                "inventory_transaction_id",
                "landed_cost_allocations",
                "inventory_transactions",
                "SET NULL",
            ),
        )
        op.create_index(
            "IX_landed_cost_allocations_firm_id",
            "landed_cost_allocations",
            ["firm_id"],
        )
        op.create_index(
            "IX_landed_cost_allocations_voucher",
            "landed_cost_allocations",
            ["voucher_id"],
        )
        op.create_index(
            "IX_landed_cost_allocations_receipt",
            "landed_cost_allocations",
            ["goods_receipt_id"],
        )


def _group_for(
    bind: sa.Connection, firm_id: object, *, code: str, kind: str, name: str
) -> object:
    """Return the firm's group for an account, creating it only if it has none."""
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


def _seed_accounts(inspector: sa.Inspector) -> None:
    """Map the valuation clearing account for every firm whose books are open."""
    if not inspector.has_table("ledger_accounts") or not inspector.has_table(
        "firm_control_accounts"
    ):
        return
    bind = op.get_bind()
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
        for purpose, code, name, kind, group_code, group_name in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
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
                # The firm used the code for something else; mapping it would
                # post a landed cost to whatever that is. Left for the firm.
                continue
            account_id = None if found is None else found[0]
            if account_id is None:
                group_id = _group_for(
                    bind, firm_id, code=group_code, kind=kind, name=group_name
                )
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
                        "group": group_id,
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
                    "purpose": purpose,
                    "account": account_id,
                },
            )


def upgrade() -> None:
    """Create the voucher tables and map the clearing account."""
    inspector = sa.inspect(op.get_bind())
    # Firm stores only: the platform store holds no receipts.
    if not inspector.has_table("goods_receipts"):
        return
    _tables(inspector)
    _seed_accounts(inspector)


def downgrade() -> None:
    """Drop the voucher tables; keep the account and its postings."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose = 'LANDED_COST_CLEARING'"
            )
        )
    for table in (
        "landed_cost_allocations",
        "landed_cost_charges",
        "landed_cost_vouchers",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
