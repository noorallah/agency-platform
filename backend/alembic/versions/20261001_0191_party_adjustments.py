"""Adjusting a party's balance without tax (backlog 74 row 2).

* ``settlements.rounding_amount``, ``bank_charges_amount`` and
  ``discount_amount``: what settled the bills on a receipt or payment without
  moving as money, each posted to its own account.
* ``party_adjustments``, ``party_adjustment_allocations`` and
  ``party_adjustment_settings``: a customer write-off, a supplier write-back
  and a set-off between the two, with the bills each clears and the firm's
  approval threshold and rounding limit.
* Three control purposes for every firm whose books are open -- new firms get
  them from ``opening_setup``: ``BANK_CHARGES`` on the existing *Bank
  Charges* (6700, indirect expenses), ``BAD_DEBTS`` on *Bad Debts* (6800,
  indirect expenses) and ``BALANCES_WRITTEN_BACK`` on *Balances Written Back*
  (4300, revenue). Only where missing, never overwriting: a purpose already
  mapped keeps its account, and an account already holding the code is the
  one mapped -- unless it is of a type the purpose cannot post to, when the
  purpose is left for the firm to map and the readiness check says so.
* ``PARTY_ADJUSTMENT_VIEW`` / ``_MANAGE`` / ``_APPROVE`` in the platform store,
  with every system role's grants reconciled -- the shape of
  ``20261001_0180``.

Idempotent throughout; firm-owned parts run per store
(``scripts/migrate_all_stores.py``). Cross-schema foreign keys are declared
only where the target exists in the store being migrated.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261001_0191"
down_revision: str | Sequence[str] | None = "20261001_0185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HEADERS = "party_adjustments"
_ALLOCATIONS = "party_adjustment_allocations"
_SETTINGS = "party_adjustment_settings"
_DEDUCTIONS = ("rounding_amount", "bank_charges_amount", "discount_amount")

#: (purpose, code, name, account type, group code, group name)
_ACCOUNTS = (
    ("BANK_CHARGES", "6700", "Bank Charges", "EXPENSE", "IEXP", "Indirect Expenses"),
    ("BAD_DEBTS", "6800", "Bad Debts", "EXPENSE", "IEXP", "Indirect Expenses"),
    (
        "BALANCES_WRITTEN_BACK",
        "4300",
        "Balances Written Back",
        "INCOME",
        "REV",
        "Revenue",
    ),
)


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


def _add_deductions(inspector: sa.Inspector) -> None:
    """Give settlements the three deduction columns where they lack them."""
    if not inspector.has_table("settlements"):
        return
    columns = {column["name"] for column in inspector.get_columns("settlements")}
    for name in _DEDUCTIONS:
        if name not in columns:
            op.add_column(
                "settlements",
                sa.Column(name, sa.Numeric(18, 2), nullable=False, server_default="0"),
            )


def _create_headers(inspector: sa.Inspector) -> None:
    """Create the adjustment table where a firm store lacks it."""
    if inspector.has_table(_HEADERS):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    constraints += _external_fk(
        inspector, "customers", "customer_id", "FK_party_adjustments_customer_id"
    )
    constraints += _external_fk(
        inspector, "vendors", "vendor_id", "FK_party_adjustments_vendor_id"
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "journal_entry_id",
        "FK_party_adjustments_journal_entry_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "reversal_journal_entry_id",
        "FK_party_adjustments_reversal_journal_entry_id",
    )
    op.create_table(
        _HEADERS,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("adjustment_number", sa.String(length=60), nullable=False),
        sa.Column("adjustment_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=True),
        sa.Column("vendor_id", UUIDType(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("receivable_transaction_id", UUIDType(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", UUIDType(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", UUIDType(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_party_adjustments"),
        sa.UniqueConstraint(
            "firm_id", "adjustment_number", name="UQ_party_adjustments_number"
        ),
        sa.CheckConstraint("amount > 0", name="CK_party_adjustments_amount_positive"),
        sa.CheckConstraint(
            "(kind = 'CUSTOMER_WRITE_OFF' AND customer_id IS NOT NULL "
            "AND vendor_id IS NULL) OR (kind = 'SUPPLIER_WRITE_BACK' "
            "AND vendor_id IS NOT NULL AND customer_id IS NULL) OR "
            "(kind = 'SET_OFF' AND customer_id IS NOT NULL "
            "AND vendor_id IS NOT NULL)",
            name="CK_party_adjustments_parties_match_kind",
        ),
        *constraints,
    )
    op.create_index("IX_party_adjustments_firm_id", _HEADERS, ["firm_id"])
    op.create_index(
        "IX_party_adjustments_firm_date", _HEADERS, ["firm_id", "adjustment_date"]
    )
    op.create_index("IX_party_adjustments_firm_status", _HEADERS, ["firm_id", "status"])
    op.create_index(
        "IX_party_adjustments_firm_customer", _HEADERS, ["firm_id", "customer_id"]
    )
    op.create_index(
        "IX_party_adjustments_firm_vendor", _HEADERS, ["firm_id", "vendor_id"]
    )


def _create_allocations(inspector: sa.Inspector) -> None:
    """Create the allocation table where a firm store lacks it."""
    if inspector.has_table(_ALLOCATIONS):
        return
    constraints: list[sa.ForeignKeyConstraint] = [
        sa.ForeignKeyConstraint(
            ["party_adjustment_id"],
            [f"{_HEADERS}.id"],
            name="FK_party_adjustment_allocations_party_adjustment_id",
            ondelete="CASCADE",
        )
    ]
    for table, column in (
        ("sales_invoices", "sales_invoice_id"),
        ("purchase_invoices", "purchase_invoice_id"),
        ("customer_opening_bills", "customer_opening_bill_id"),
        ("vendor_opening_bills", "vendor_opening_bill_id"),
    ):
        constraints += _external_fk(
            inspector, table, column, f"FK_party_adjustment_allocations_{column}"
        )
    op.create_table(
        _ALLOCATIONS,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("party_adjustment_id", UUIDType(), nullable=False),
        sa.Column("sales_invoice_id", UUIDType(), nullable=True),
        sa.Column("purchase_invoice_id", UUIDType(), nullable=True),
        sa.Column("customer_opening_bill_id", UUIDType(), nullable=True),
        sa.Column("vendor_opening_bill_id", UUIDType(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_party_adjustment_allocations"),
        sa.CheckConstraint(
            "amount > 0", name="CK_party_adjustment_allocations_positive"
        ),
        sa.UniqueConstraint(
            "party_adjustment_id",
            "sales_invoice_id",
            name="UQ_party_adjustment_allocations_sales_invoice",
        ),
        sa.UniqueConstraint(
            "party_adjustment_id",
            "purchase_invoice_id",
            name="UQ_party_adjustment_allocations_purchase_invoice",
        ),
        sa.UniqueConstraint(
            "party_adjustment_id",
            "customer_opening_bill_id",
            name="UQ_party_adjustment_allocations_customer_opening_bill",
        ),
        sa.UniqueConstraint(
            "party_adjustment_id",
            "vendor_opening_bill_id",
            name="UQ_party_adjustment_allocations_vendor_opening_bill",
        ),
        *constraints,
    )
    op.create_index(
        "IX_party_adjustment_allocations_firm_id", _ALLOCATIONS, ["firm_id"]
    )
    op.create_index(
        "IX_party_adjustment_allocations_party_adjustment_id",
        _ALLOCATIONS,
        ["party_adjustment_id"],
    )
    for name, column in (
        ("IX_party_adjustment_allocations_sales", "sales_invoice_id"),
        ("IX_party_adjustment_allocations_purchase", "purchase_invoice_id"),
        (
            "IX_party_adjustment_allocations_customer_opening",
            "customer_opening_bill_id",
        ),
        ("IX_party_adjustment_allocations_vendor_opening", "vendor_opening_bill_id"),
    ):
        op.create_index(name, _ALLOCATIONS, ["firm_id", column])


def _create_settings(inspector: sa.Inspector) -> None:
    """Create the settings table where a firm store lacks it."""
    if inspector.has_table(_SETTINGS):
        return
    op.create_table(
        _SETTINGS,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "approval_threshold",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="1000.00",
        ),
        sa.Column(
            "rounding_limit", sa.Numeric(18, 2), nullable=False, server_default="10.00"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_party_adjustment_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_party_adjustment_settings_firm"),
        sa.CheckConstraint(
            "approval_threshold >= 0",
            name="CK_party_adjustment_settings_threshold",
        ),
        sa.CheckConstraint(
            "rounding_limit >= 0", name="CK_party_adjustment_settings_rounding"
        ),
    )
    op.create_index("IX_party_adjustment_settings_firm_id", _SETTINGS, ["firm_id"])


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
    """Map the three new purposes for every firm whose books are open."""
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
                # post bad debts to whatever that is. Left for the firm.
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
_roles = sa.table("roles", sa.column("id", UUIDType()), sa.column("code", sa.String()))
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert missing system permissions and reconcile system role grants."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        existing[code] = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=existing[code],
                code=code,
                name=code.replace("_", " ").title(),
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
    granted = set(
        bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        )
        .tuples()
        .all()
    )
    for role_code, codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
            permission_id = existing.get(code)
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


def upgrade() -> None:
    """Add the deductions, the adjustment tables, the accounts and the codes."""
    inspector = sa.inspect(op.get_bind())
    _add_deductions(inspector)
    # A firm store is one that holds the bills an adjustment clears.
    if inspector.has_table("sales_invoices"):
        _create_headers(inspector)
        _create_allocations(sa.inspect(op.get_bind()))
        _create_settings(sa.inspect(op.get_bind()))
    _seed_accounts(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the tables, the columns and the three mappings; keep the accounts.

    The accounts may carry postings by then. The permission codes stay, as
    every such migration's do.
    """
    inspector = sa.inspect(op.get_bind())
    for table in (_ALLOCATIONS, _HEADERS, _SETTINGS):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("settlements"):
        columns = {column["name"] for column in inspector.get_columns("settlements")}
        for name in _DEDUCTIONS:
            if name in columns:
                op.drop_column("settlements", name)
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('BANK_CHARGES', 'BAD_DEBTS', 'BALANCES_WRITTEN_BACK')"
            )
        )
