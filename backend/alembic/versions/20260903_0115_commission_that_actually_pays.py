"""Commission stops reporting and starts paying.

`app/commission` answered what a period earned and stopped there, so the
number lived on a screen and never in the books. `commission_payouts` is the
record of a debt: accrued from the report, adjusted while it is still a draft,
approved into the ledger, and paid.

Three things come with it.

**The table.** `salesman_id` is NOT NULL, unlike a rule's -- a rule can belong
to the firm as a default, but there is nobody to pay a payout that names
nobody. The foreign keys to `users`, `ledger_accounts` and `journal_entries`
are declared only where the target is present, which is the `_external_fk`
shape from `20260809_0042`: `users` lives only in the platform schema.

**`COMMISSION_PAY`.** A code a router enforces and the catalogue does not
define has no permission row, so it cannot be attached to any role and the
endpoint quietly becomes platform-admin-only. Deliberately not granted to
`SALES_MANAGER`: whoever states a debt should not also be the one who moves
the cash, and a sales manager holding both could pay their own team.

**The two ledger accounts.** `5600 Commission Expense` and
`2400 Commission Payable`, mapped to the new control purposes for every firm
that already has a chart. Without them approval would refuse, which is the
first thing anybody does with a payout. Two accounts rather than one, because
an approved payout is a liability that outlives the month it was earned in --
booking the expense straight against cash would say the firm owes nobody the
moment it recognises the cost.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0115
Revises: 20260903_0114
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0115"
down_revision: str | Sequence[str] | None = "20260903_0114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_payouts"
_NEW_CODES = ("COMMISSION_PAY",)

#: The two purposes, and the account each one is created as where a firm's
#: chart does not already nominate something.
_ACCOUNTS = (
    ("COMMISSION_EXPENSE", "5600", "Commission Expense", "EXPENSE", "EXP"),
    ("COMMISSION_PAYABLE", "2400", "Commission Payable", "LIABILITY", "CL"),
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


def _create_table(inspector: sa.Inspector) -> None:
    """Create the payout table where a firm store does not have it."""
    if inspector.has_table(_TABLE):
        return
    # A store that does not trade has nothing to pay commission on.
    if not inspector.has_table("sales_invoices"):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    constraints += _external_fk(
        inspector, "users", "salesman_id", "FK_commission_payouts_salesman_id"
    )
    constraints += _external_fk(
        inspector,
        "ledger_accounts",
        "money_account_id",
        "FK_commission_payouts_money_account_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "journal_entry_id",
        "FK_commission_payouts_journal_entry_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "payment_journal_entry_id",
        "FK_commission_payouts_payment_journal_entry_id",
    )
    op.create_table(
        _TABLE,
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
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("salesman_id", UUIDType(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "basis", sa.String(length=20), nullable=False, server_default="COLLECTED"
        ),
        sa.Column(
            "measured_amount", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "earned_amount", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "adjustment_amount", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column("adjustment_reason", sa.Text(), nullable=True),
        sa.Column(
            "payable_amount", sa.Numeric(18, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("accrued_on", sa.Date(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("money_account_id", UUIDType(), nullable=True),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("payment_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "period_end >= period_start", name="CK_commission_payouts_period_order"
        ),
        sa.CheckConstraint(
            "earned_amount >= 0", name="CK_commission_payouts_earned_amount"
        ),
        *constraints,
    )
    op.create_index("IX_commission_payouts_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_commission_payouts_firm_salesman", _TABLE, ["firm_id", "salesman_id"]
    )
    op.create_index(
        "IX_commission_payouts_firm_period", _TABLE, ["firm_id", "period_start"]
    )
    op.create_index("IX_commission_payouts_firm_status", _TABLE, ["firm_id", "status"])


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define `COMMISSION_PAY` and grant it where the seed says it belongs."""
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
    """Give every firm somewhere to book commission.

    Follows `20260814_0080`, which had to do the same for opening stock: a
    purpose with no mapping is an error naming the purpose, never a fallback,
    so an unmapped firm simply could not approve a payout.
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
    """Create the payout table, its permission, and the accounts it posts to."""
    inspector = sa.inspect(op.get_bind())
    _create_table(inspector)
    _seed_permissions(inspector)
    _seed_control_accounts(inspector)


def downgrade() -> None:
    """Drop the payout table and unmap the two purposes.

    The permission code and the ledger accounts stay: removing the code would
    strip grants an administrator may since have made to custom roles, and an
    account may have postings against it by then.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("firm_control_accounts"):
        op.get_bind().execute(
            sa.text(
                "DELETE FROM firm_control_accounts WHERE purpose IN "
                "('COMMISSION_EXPENSE', 'COMMISSION_PAYABLE')"
            )
        )
