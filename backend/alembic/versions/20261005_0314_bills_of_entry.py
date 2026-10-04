"""Bills of Entry, customs duty and IGST on imports (PG-12 part B, backlog 86 #5).

* ``bills_of_entry``, ``bill_of_entry_lines``, ``bill_of_entry_documents``
  (the bills and receipts a Bill of Entry names, by bare id) and
  ``bill_of_entry_allocations`` (the duty each receipt line carried).
* ``CUSTOMS_PAYABLE`` mapped to *Customs Duty Payable* (2800, liability) and
  ``CUSTOMS_DUTY`` to *Customs Duty* (5220, expense) for every firm whose
  books are open, the shape of ``20261005_0313``: only where missing, never
  overwriting.
* ``BILL_OF_ENTRY_VIEW`` and ``BILL_OF_ENTRY_MANAGE`` seeded and the system
  roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each table and
index is created only in a firm store (one holding ``purchase_invoices``) that
lacks it. No ``firm_id`` foreign key: ``firms`` lives only in the platform
store.

Revision ID: 20261005_0314
Revises: 20261005_0313
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261005_0314"
down_revision: str | Sequence[str] | None = "20261005_0313"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)

_TABLES = (
    "bill_of_entry_allocations",
    "bill_of_entry_documents",
    "bill_of_entry_lines",
    "bills_of_entry",
)

#: (purpose, code, name, account type, group code, group name, balance sheet)
_ACCOUNTS = (
    (
        "CUSTOMS_PAYABLE",
        "2800",
        "Customs Duty Payable",
        "LIABILITY",
        "CL",
        "Current Liabilities",
        True,
    ),
    (
        "CUSTOMS_DUTY",
        "5220",
        "Customs Duty",
        "EXPENSE",
        "EXP",
        "Direct Expenses",
        False,
    ),
)


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _seed_permissions() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        permission_id = uuid4()
        existing[code] = permission_id
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )

    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
    }
    granted = {
        (role_id, permission_id)
        for role_id, permission_id in bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        ).all()
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for permission_code in permission_codes:
            permission_id = existing.get(permission_code)
            if permission_id is None or (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named for its referring column."""
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"FK_{table}_{column}", ondelete=ondelete
    )


def _money(name: str) -> sa.Column[object]:
    """Return a rupee column that reads zero until written."""
    return sa.Column(
        name, sa.Numeric(18, 2), server_default=sa.text("0"), nullable=False
    )


def _create_bills_of_entry() -> None:
    """Create the header."""
    op.create_table(
        "bills_of_entry",
        *_base_columns(),
        sa.Column("document_number", sa.String(60), nullable=False),
        sa.Column("boe_number", sa.String(30), nullable=False),
        sa.Column("boe_date", sa.Date(), nullable=False),
        sa.Column("port_code", sa.String(10), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        _money("assessable_value"),
        _money("basic_customs_duty"),
        _money("social_welfare_surcharge"),
        _money("igst_amount"),
        _money("cess_amount"),
        _money("total_duty"),
        _money("inventory_amount"),
        _money("cogs_amount"),
        _money("expense_amount"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", UUIDType(), nullable=True),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_bills_of_entry"),
        _fk("bills_of_entry", "vendor_id", "vendors", "RESTRICT"),
        _fk("bills_of_entry", "branch_id", "branches", "RESTRICT"),
        _fk("bills_of_entry", "journal_entry_id", "journal_entries", "RESTRICT"),
    )
    op.create_index("IX_bills_of_entry_firm_id", "bills_of_entry", ["firm_id"])
    op.create_index(
        "IX_bills_of_entry_firm_date", "bills_of_entry", ["firm_id", "boe_date"]
    )
    op.create_index(
        "IX_bills_of_entry_firm_vendor_status",
        "bills_of_entry",
        ["firm_id", "vendor_id", "status"],
    )
    op.create_index(
        "UQ_bills_of_entry_number_active",
        "bills_of_entry",
        ["firm_id", "document_number"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def _create_lines() -> None:
    """Create the lines."""
    op.create_table(
        "bill_of_entry_lines",
        *_base_columns(),
        sa.Column("bill_of_entry_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("assessable_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("bcd_rate", sa.Numeric(9, 4), nullable=True),
        _money("bcd_amount"),
        sa.Column("sws_rate", sa.Numeric(9, 4), nullable=True),
        _money("sws_amount"),
        sa.Column("igst_rate", sa.Numeric(9, 4), nullable=True),
        _money("igst_amount"),
        _money("cess_amount"),
        _money("total_duty"),
        _money("inventory_amount"),
        _money("cogs_amount"),
        _money("expense_amount"),
        sa.PrimaryKeyConstraint("id", name="PK_bill_of_entry_lines"),
        _fk("bill_of_entry_lines", "bill_of_entry_id", "bills_of_entry", "CASCADE"),
        _fk("bill_of_entry_lines", "product_id", "products", "RESTRICT"),
    )
    op.create_index(
        "IX_bill_of_entry_lines_firm_id", "bill_of_entry_lines", ["firm_id"]
    )
    op.create_index(
        "IX_bill_of_entry_lines_boe", "bill_of_entry_lines", ["bill_of_entry_id"]
    )
    op.create_index(
        "IX_bill_of_entry_lines_firm_product",
        "bill_of_entry_lines",
        ["firm_id", "product_id"],
    )


def _create_documents() -> None:
    """Create the links to the bills and receipts."""
    op.create_table(
        "bill_of_entry_documents",
        *_base_columns(),
        sa.Column("bill_of_entry_id", UUIDType(), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("document_id", UUIDType(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_bill_of_entry_documents"),
        _fk("bill_of_entry_documents", "bill_of_entry_id", "bills_of_entry", "CASCADE"),
    )
    op.create_index(
        "IX_bill_of_entry_documents_firm_id", "bill_of_entry_documents", ["firm_id"]
    )
    op.create_index(
        "IX_bill_of_entry_documents_boe",
        "bill_of_entry_documents",
        ["bill_of_entry_id"],
    )
    op.create_index(
        "IX_bill_of_entry_documents_document",
        "bill_of_entry_documents",
        ["document_id"],
    )


def _create_allocations() -> None:
    """Create the duty each receipt line carried."""
    table = "bill_of_entry_allocations"
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("bill_of_entry_id", UUIDType(), nullable=False),
        sa.Column("bill_of_entry_line_id", UUIDType(), nullable=False),
        sa.Column("goods_receipt_id", UUIDType(), nullable=False),
        sa.Column("goods_receipt_line_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("inventory_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("cogs_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_bill_of_entry_allocations"),
        _fk(table, "bill_of_entry_id", "bills_of_entry", "CASCADE"),
        _fk(table, "bill_of_entry_line_id", "bill_of_entry_lines", "CASCADE"),
        _fk(table, "goods_receipt_id", "goods_receipts", "RESTRICT"),
        _fk(table, "goods_receipt_line_id", "goods_receipt_lines", "RESTRICT"),
        _fk(table, "inventory_transaction_id", "inventory_transactions", "SET NULL"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    op.create_index(f"IX_{table}_boe", table, ["bill_of_entry_id"])
    op.create_index(f"IX_{table}_receipt", table, ["goods_receipt_id"])


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
    """Map the customs accounts for every firm whose books are open."""
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
        for purpose, code, name, kind, group_code, group_name, sheet in _ACCOUNTS:
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
                # post customs duty to whatever that is. Left for the firm.
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
                        ":kind, :sheet, :pl, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": kind,
                        "sheet": sheet,
                        "pl": not sheet,
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
    """Create the tables where a firm store lacks them; map accounts; seed codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_invoices"):
        if not inspector.has_table("bills_of_entry"):
            _create_bills_of_entry()
        if not inspector.has_table("bill_of_entry_lines"):
            _create_lines()
        if not inspector.has_table("bill_of_entry_documents"):
            _create_documents()
        if not inspector.has_table("bill_of_entry_allocations"):
            _create_allocations()
        _seed_accounts(inspector)
    _seed_permissions()


def downgrade() -> None:
    """Drop the tables and the mappings; keep the accounts and permissions."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts "
                "WHERE purpose IN ('CUSTOMS_PAYABLE', 'CUSTOMS_DUTY')"
            )
        )
    for table in _TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
