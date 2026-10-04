"""Fixed assets: classes, the register, depreciation runs (PG-13, backlog 86 #7).

* ``asset_classes`` (Companies Act method and rate or life, residual %,
  Income-tax block rate, account overrides), ``fixed_assets`` (the register),
  ``depreciation_runs`` and ``depreciation_run_lines``.
* ``purchase_invoice_lines.is_capital_goods`` and ``asset_class_id``: a bill
  line that raises an asset instead of entering stock.
* ``FIXED_ASSET_COST`` (1500), ``ACCUMULATED_DEPRECIATION`` (1590, both in a
  *Fixed Assets* group), ``DEPRECIATION_EXPENSE`` (6950) and
  ``ASSET_DISPOSAL_GAIN_LOSS`` (4960) mapped for every firm whose books are
  open, the shape of ``20261005_0314``: only where missing, never overwriting.
* The five default asset classes for those firms, by code, only where the
  firm never had the code.
* ``FIXED_ASSET_VIEW`` and ``FIXED_ASSET_MANAGE`` seeded and the system roles
  reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each table,
column and index is created only in a firm store (one holding
``purchase_invoices``) that lacks it. No ``firm_id`` foreign key: ``firms``
lives only in the platform store.

Revision ID: 20261005_0315
Revises: 20261005_0314
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261005_0315"
down_revision: str | Sequence[str] | None = "20261005_0314"
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
    "depreciation_run_lines",
    "depreciation_runs",
    "fixed_assets",
    "asset_classes",
)

#: (purpose, code, name, account type, group code, group name, balance sheet)
_ACCOUNTS = (
    (
        "FIXED_ASSET_COST",
        "1500",
        "Fixed Assets",
        "ASSET",
        "FA",
        "Fixed Assets",
        True,
    ),
    (
        "ACCUMULATED_DEPRECIATION",
        "1590",
        "Accumulated Depreciation",
        "ASSET",
        "FA",
        "Fixed Assets",
        True,
    ),
    (
        "DEPRECIATION_EXPENSE",
        "6950",
        "Depreciation",
        "EXPENSE",
        "IEXP",
        "Indirect Expenses",
        False,
    ),
    (
        "ASSET_DISPOSAL_GAIN_LOSS",
        "4960",
        "Profit/Loss on Sale of Assets",
        "INCOME",
        "REV",
        "Revenue",
        False,
    ),
)

#: (code, name, useful life in years, Income-tax block rate %), as
#: ``app/fixed_assets/services/defaults.py`` seeds them with the books.
_CLASSES = (
    ("PLANT", "Plant and Machinery", 15, 15),
    ("FURNITURE", "Furniture and Fittings", 10, 10),
    ("COMPUTERS", "Computers", 3, 40),
    ("VEHICLES", "Motor Vehicles", 8, 15),
    ("OFFICE_EQUIPMENT", "Office Equipment", 5, 15),
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


def _partial_unique(name: str, table: str, columns: list[str]) -> None:
    """Create a unique index over live rows only."""
    op.create_index(
        name,
        table,
        columns,
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def _create_classes() -> None:
    """Create the asset classes."""
    table = "asset_classes"
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("depreciation_method", sa.String(10), nullable=False),
        sa.Column("rate_percent", sa.Numeric(9, 4), nullable=True),
        sa.Column("useful_life_years", sa.Numeric(6, 2), nullable=True),
        sa.Column(
            "residual_percent",
            sa.Numeric(9, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "it_block_rate_percent",
            sa.Numeric(9, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("asset_account_id", UUIDType(), nullable=True),
        sa.Column("accumulated_depreciation_account_id", UUIDType(), nullable=True),
        sa.Column("depreciation_expense_account_id", UUIDType(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_asset_classes"),
        _fk(table, "asset_account_id", "ledger_accounts", "RESTRICT"),
        _fk(
            table, "accumulated_depreciation_account_id", "ledger_accounts", "RESTRICT"
        ),
        _fk(table, "depreciation_expense_account_id", "ledger_accounts", "RESTRICT"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    _partial_unique("UQ_asset_classes_code_active", table, ["firm_id", "code"])


def _create_assets() -> None:
    """Create the register."""
    table = "fixed_assets"
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("asset_number", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("asset_class_id", UUIDType(), nullable=False),
        sa.Column("purchase_invoice_id", UUIDType(), nullable=True),
        sa.Column("purchase_invoice_line_id", UUIDType(), nullable=True),
        sa.Column("vendor_id", UUIDType(), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("put_to_use_date", sa.Date(), nullable=False),
        sa.Column(
            "quantity", sa.Numeric(18, 4), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("cost", sa.Numeric(18, 2), nullable=False),
        _money("residual_value"),
        _money("opening_accumulated_depreciation"),
        sa.Column("opening_as_of", sa.Date(), nullable=True),
        sa.Column("opening_it_wdv", sa.Numeric(18, 2), nullable=True),
        sa.Column("branch_id", UUIDType(), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("disposed_on", sa.Date(), nullable=True),
        sa.Column("sale_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("disposal_method", sa.String(10), nullable=True),
        sa.Column("disposal_reason", sa.Text(), nullable=True),
        sa.Column("disposal_gain_loss", sa.Numeric(18, 2), nullable=True),
        sa.Column("disposal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_fixed_assets"),
        _fk(table, "asset_class_id", "asset_classes", "RESTRICT"),
        _fk(table, "vendor_id", "vendors", "RESTRICT"),
        _fk(table, "branch_id", "branches", "RESTRICT"),
        _fk(table, "disposal_journal_entry_id", "journal_entries", "RESTRICT"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    op.create_index("IX_fixed_assets_firm_class", table, ["firm_id", "asset_class_id"])
    op.create_index("IX_fixed_assets_firm_status", table, ["firm_id", "status"])
    op.create_index("IX_fixed_assets_invoice", table, ["purchase_invoice_id"])
    _partial_unique("UQ_fixed_assets_number_active", table, ["firm_id", "asset_number"])


def _create_runs() -> None:
    """Create the depreciation runs."""
    table = "depreciation_runs"
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("run_number", sa.String(30), nullable=False),
        sa.Column("run_type", sa.String(20), nullable=False),
        sa.Column("book", sa.String(20), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        _money("total_amount"),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_depreciation_runs"),
        _fk(table, "journal_entry_id", "journal_entries", "RESTRICT"),
        _fk(table, "reversal_journal_entry_id", "journal_entries", "RESTRICT"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    op.create_index(
        "IX_depreciation_runs_firm_period", table, ["firm_id", "period_from"]
    )
    _partial_unique(
        "UQ_depreciation_runs_number_active", table, ["firm_id", "run_number"]
    )


def _create_run_lines() -> None:
    """Create what each run charged each asset."""
    table = "depreciation_run_lines"
    op.create_table(
        table,
        *_base_columns(),
        sa.Column("depreciation_run_id", UUIDType(), nullable=False),
        sa.Column("fixed_asset_id", UUIDType(), nullable=False),
        sa.Column("asset_class_id", UUIDType(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("opening_book_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_depreciation_run_lines"),
        _fk(table, "depreciation_run_id", "depreciation_runs", "CASCADE"),
        _fk(table, "fixed_asset_id", "fixed_assets", "RESTRICT"),
        _fk(table, "asset_class_id", "asset_classes", "RESTRICT"),
    )
    op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
    op.create_index("IX_depreciation_run_lines_run", table, ["depreciation_run_id"])
    op.create_index(
        "IX_depreciation_run_lines_asset", table, ["fixed_asset_id", "to_date"]
    )


def _add_line_columns(inspector: sa.Inspector) -> None:
    """Give purchase-bill lines the capital-goods flag and asset class."""
    columns = {
        column["name"] for column in inspector.get_columns("purchase_invoice_lines")
    }
    if "is_capital_goods" not in columns:
        op.add_column(
            "purchase_invoice_lines",
            sa.Column(
                "is_capital_goods",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "asset_class_id" not in columns:
        op.add_column(
            "purchase_invoice_lines",
            sa.Column("asset_class_id", UUIDType(), nullable=True),
        )
        op.create_foreign_key(
            "FK_purchase_invoice_lines_asset_class_id",
            "purchase_invoice_lines",
            "asset_classes",
            ["asset_class_id"],
            ["id"],
            ondelete="RESTRICT",
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
    """Map the fixed-asset accounts for every firm whose books are open."""
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
                # post depreciation to whatever that is. Left for the firm.
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


def _seed_classes(inspector: sa.Inspector) -> None:
    """Give every firm whose books are open the default classes it never had."""
    if not inspector.has_table("ledger_accounts"):
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
        used = set(
            bind.execute(
                sa.text("SELECT code FROM asset_classes WHERE firm_id = :firm"),
                {"firm": firm_id},
            )
            .scalars()
            .all()
        )
        for code, name, life, block_rate in _CLASSES:
            if code in used:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO asset_classes (id, firm_id, code, name, "
                    "depreciation_method, useful_life_years, residual_percent, "
                    "it_block_rate_percent, is_active, is_deleted, version, "
                    "created_at, updated_at) VALUES (:id, :firm, :code, :name, "
                    "'SLM', :life, 5, :rate, true, false, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "firm": firm_id,
                    "code": code,
                    "name": name,
                    "life": life,
                    "rate": block_rate,
                },
            )


def upgrade() -> None:
    """Create what a firm store lacks; map accounts; seed classes and codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_invoices"):
        if not inspector.has_table("asset_classes"):
            _create_classes()
        if not inspector.has_table("fixed_assets"):
            _create_assets()
        if not inspector.has_table("depreciation_runs"):
            _create_runs()
        if not inspector.has_table("depreciation_run_lines"):
            _create_run_lines()
        _add_line_columns(inspector)
        _seed_accounts(inspector)
        _seed_classes(inspector)
    _seed_permissions()


def downgrade() -> None:
    """Drop the tables, the line columns and the mappings; keep accounts, codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('FIXED_ASSET_COST', 'ACCUMULATED_DEPRECIATION', "
                "'DEPRECIATION_EXPENSE', 'ASSET_DISPOSAL_GAIN_LOSS')"
            )
        )
    if inspector.has_table("purchase_invoice_lines"):
        columns = {
            column["name"] for column in inspector.get_columns("purchase_invoice_lines")
        }
        if "asset_class_id" in columns:
            op.drop_constraint(
                "FK_purchase_invoice_lines_asset_class_id",
                "purchase_invoice_lines",
                type_="foreignkey",
            )
            op.drop_column("purchase_invoice_lines", "asset_class_id")
        if "is_capital_goods" in columns:
            op.drop_column("purchase_invoice_lines", "is_capital_goods")
    for table in _TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
