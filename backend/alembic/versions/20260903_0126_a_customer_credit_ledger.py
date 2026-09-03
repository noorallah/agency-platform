"""Credit a customer earns on what they buy, and spends on what they buy next.

Loyalty points and cashback are the same subsystem seen twice -- a balance the
customer holds and can spend -- so this is one ledger rather than two. What a
firm calls it is a matter of the conversion rate: a point worth one rupee is
cashback, and a point worth less is a points scheme.

**Redeeming settles the bill; it does not discount it.** The supply is worth
what it is worth and the full tax is charged on it; the customer pays part of it
with credit the firm already owes them, exactly as a gift voucher works. The
alternative -- treating a redemption as a discount -- reduces the taxable value
and so the GST the firm collects, which is a decision about tax rather than
about loyalty and not one this module should make quietly.

Two accounts follow from that. Points cost the firm money **when they are
earned**: `Dr Loyalty Expense / Cr Loyalty Payable` at 5700 and 2600, so a
scheme's cost lands in the month it was incurred rather than whenever customers
happen to collect. Redeeming is `Dr Loyalty Payable / Cr Accounts Receivable`.

There is no balance column. The balance is the sum of the ledger, the way an
invoice's outstanding is the sum of its allocations.

Off by default, so shipping this credits nobody until a firm says what its
scheme is.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0126
Revises: 20260903_0125
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0126"
down_revision: str | Sequence[str] | None = "20260903_0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = "loyalty_settings"
_ENTRIES = "loyalty_entries"
_NEW_CODES = ("LOYALTY_VIEW", "LOYALTY_MANAGE", "LOYALTY_MANAGE_SETTINGS")

_ACCOUNTS = (
    ("LOYALTY_EXPENSE", "5700", "Loyalty Expense", "EXPENSE", "EXP"),
    ("LOYALTY_PAYABLE", "2600", "Loyalty Payable", "LIABILITY", "CL"),
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


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


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
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP` because a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails -- `20260903_0114` had to repair every store for
    exactly that.
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


def _create_tables(inspector: sa.Inspector) -> None:
    """Create the loyalty tables where a firm store lacks them."""
    if not inspector.has_table("customers"):
        return
    if not inspector.has_table(_SETTINGS):
        op.create_table(
            _SETTINGS,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            # False, so shipping this credits nobody until a firm says what
            # its scheme is.
            sa.Column(
                "is_enabled", sa.Boolean(), nullable=False, server_default="false"
            ),
            sa.Column(
                "points_per_amount",
                sa.Numeric(12, 4),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "amount_per_point",
                sa.Numeric(12, 4),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "minimum_redemption_points",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            # Nullable: points that never expire is a real choice, and zero
            # would mean they expire the day they are earned.
            sa.Column("expiry_months", sa.Integer(), nullable=True),
            sa.UniqueConstraint("firm_id", name="UQ_loyalty_settings_firm"),
            sa.CheckConstraint(
                "points_per_amount >= 0", name="CK_loyalty_settings_earn_rate"
            ),
            sa.CheckConstraint(
                "amount_per_point >= 0", name="CK_loyalty_settings_point_value"
            ),
        )
        op.create_index("IX_loyalty_settings_firm_id", _SETTINGS, ["firm_id"])

    if inspector.has_table(_ENTRIES):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    constraints += _external_fk(
        inspector, "customers", "customer_id", "FK_loyalty_entries_customer_id"
    )
    constraints += _external_fk(
        inspector,
        "sales_invoices",
        "sales_invoice_id",
        "FK_loyalty_entries_sales_invoice_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "journal_entry_id",
        "FK_loyalty_entries_journal_entry_id",
    )
    op.create_table(
        _ENTRIES,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        # Signed, so the balance is one sum rather than a set of rules about
        # which kinds add and which subtract.
        sa.Column("points", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("sales_invoice_id", UUIDType(), nullable=True),
        sa.Column("earned_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("reverses_id", UUIDType(), nullable=True),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.CheckConstraint("points <> 0", name="CK_loyalty_entries_points_nonzero"),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            [f"{_ENTRIES}.id"],
            name="FK_loyalty_entries_reverses_id",
            ondelete="RESTRICT",
        ),
        *constraints,
    )
    op.create_index("IX_loyalty_entries_firm_id", _ENTRIES, ["firm_id"])
    op.create_index(
        "IX_loyalty_entries_firm_customer", _ENTRIES, ["firm_id", "customer_id"]
    )
    op.create_index(
        "IX_loyalty_entries_firm_expiry", _ENTRIES, ["firm_id", "expires_on"]
    )
    op.create_index(
        "IX_loyalty_entries_firm_invoice", _ENTRIES, ["firm_id", "sales_invoice_id"]
    )


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the three codes and grant them where the seed says."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code).where(
                _permissions.c.code.in_(_NEW_CODES)
            )
        ).all()
    }
    for code in _NEW_CODES:
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
        for code in _NEW_CODES:
            if code not in permission_codes:
                continue
            permission_id = existing[code]
            if (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


def _seed_control_accounts(inspector: sa.Inspector) -> None:
    """Give every firm somewhere to book a scheme's cost and its liability.

    Follows `20260903_0115` and `20260903_0120`: a purpose with no mapping is
    an error naming the purpose, never a fallback, so an unmapped firm could
    not approve an invoice once the scheme was switched on.
    """
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
        for purpose, code, name, account_type, group_code in _ACCOUNTS:
            mapped = bind.execute(
                sa.text(
                    "SELECT id FROM firm_control_accounts WHERE firm_id = :firm "
                    "AND purpose = :purpose AND is_deleted = false"
                ),
                {"firm": firm_id, "purpose": purpose},
            ).scalar()
            if mapped is not None:
                continue
            group_id = bind.execute(
                sa.text(
                    "SELECT id FROM account_groups WHERE firm_id = :firm "
                    "AND account_type = :kind AND is_deleted = false "
                    "ORDER BY code LIMIT 1"
                ),
                {"firm": firm_id, "kind": account_type},
            ).scalar()
            if group_id is None:
                group_id = uuid4()
                bind.execute(
                    sa.text(
                        "INSERT INTO account_groups (id, firm_id, code, name, "
                        "account_type, is_active, is_deleted, version, "
                        "created_at, updated_at) VALUES (:id, :firm, :code, "
                        ":name, :kind, true, false, 1, now(), now())"
                    ),
                    {
                        "id": group_id,
                        "firm": firm_id,
                        "code": group_code,
                        "name": name,
                        "kind": account_type,
                    },
                )
            account_id = bind.execute(
                sa.text(
                    "SELECT id FROM ledger_accounts WHERE firm_id = :firm "
                    "AND code = :code AND is_deleted = false"
                ),
                {"firm": firm_id, "code": code},
            ).scalar()
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
                        ":kind, :balance_sheet, :profit_loss, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": account_type,
                        "balance_sheet": account_type == "LIABILITY",
                        "profit_loss": account_type == "EXPENSE",
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
    """Create the ledger, its permissions, and the accounts it posts to."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _seed_permissions(inspector)
    _seed_control_accounts(inspector)


def downgrade() -> None:
    """Drop the ledger and the mappings, leaving the permission codes.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than three extra catalogue rows.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_ENTRIES):
        op.drop_table(_ENTRIES)
    if inspector.has_table(_SETTINGS):
        op.drop_table(_SETTINGS)
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('LOYALTY_EXPENSE', 'LOYALTY_PAYABLE')"
            )
        )
