"""Tax collected at source on sale consideration, under section 206C(1H).

Two tables and one account. `tcs_settings` holds the firm's parameters -- the
rate and the thresholds are set by a Finance Act and have already changed
once, so they are columns rather than constants. `tcs_collections` holds one
row per receipt that attracted the tax, with the figures that decided the
amount stored beside it: the question asked of the table months later is "why
is this number what it is", and re-deriving it against today's settings would
answer about today.

**Nothing is collected from anybody by this migration.** `is_enabled` defaults
to false and `preceding_year_turnover` to zero, so an existing firm goes on
exactly as before until somebody states that its turnover puts it in scope.
That matters more here than usual: this tax raises what a customer owes, so a
default that switched it on would silently add a charge to every collection.

The two permission codes go in here as well. A code a router enforces and the
catalogue does not define has no permission row, so the endpoint quietly
becomes platform-admin-only. `TCS_MANAGE` is not granted to `SALES_MANAGER`:
the role a rule constrains must not be able to switch it off.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0120
Revises: 20260903_0119
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0120"
down_revision: str | Sequence[str] | None = "20260903_0119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = "tcs_settings"
_COLLECTIONS = "tcs_collections"
_NEW_CODES = ("TCS_VIEW", "TCS_MANAGE")

#: Not 2200, which is Output Tax. TCS is not GST: it is filed on a different
#: return on a different cycle, and netting the two would put a quarterly
#: payment inside a monthly one.
_ACCOUNTS = (("TCS_PAYABLE", "2500", "TCS Payable", "LIABILITY", "CL"),)

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
    """Create the TCS tables where a firm store lacks them."""
    if not inspector.has_table("settlements"):
        return
    if not inspector.has_table(_SETTINGS):
        op.create_table(
            _SETTINGS,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column(
                "section_code",
                sa.String(length=20),
                nullable=False,
                server_default="206C_1H",
            ),
            # False, so an existing firm goes on exactly as before. This tax
            # raises what a customer owes, and a default that switched it on
            # would add a charge to every collection without anybody asking.
            sa.Column(
                "is_enabled", sa.Boolean(), nullable=False, server_default="false"
            ),
            sa.Column(
                "threshold_amount",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="5000000",
            ),
            sa.Column(
                "rate_percent", sa.Numeric(6, 3), nullable=False, server_default="0.1"
            ),
            sa.Column(
                "rate_without_pan_percent",
                sa.Numeric(6, 3),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "preceding_year_turnover",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "seller_turnover_threshold",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="100000000",
            ),
            sa.UniqueConstraint("firm_id", name="UQ_tcs_settings_firm"),
            sa.CheckConstraint(
                "threshold_amount >= 0", name="CK_tcs_settings_threshold"
            ),
            sa.CheckConstraint(
                "rate_percent >= 0 AND rate_percent <= 100", name="CK_tcs_settings_rate"
            ),
            sa.CheckConstraint(
                "rate_without_pan_percent >= 0 AND rate_without_pan_percent <= 100",
                name="CK_tcs_settings_rate_without_pan",
            ),
        )
        op.create_index("IX_tcs_settings_firm_id", _SETTINGS, ["firm_id"])

    if inspector.has_table(_COLLECTIONS):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    constraints += _external_fk(
        inspector, "customers", "customer_id", "FK_tcs_collections_customer_id"
    )
    constraints += _external_fk(
        inspector, "settlements", "settlement_id", "FK_tcs_collections_settlement_id"
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "journal_entry_id",
        "FK_tcs_collections_journal_entry_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "reversal_journal_entry_id",
        "FK_tcs_collections_reversal_journal_entry_id",
    )
    op.create_table(
        _COLLECTIONS,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("settlement_id", UUIDType(), nullable=False),
        sa.Column("financial_year_start", sa.Date(), nullable=False),
        sa.Column("collected_on", sa.Date(), nullable=False),
        sa.Column("consideration_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("cumulative_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("rate_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("without_pan", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tcs_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="COLLECTED"
        ),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("reversal_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("receivable_transaction_id", UUIDType(), nullable=True),
        # One collection per receipt. A second would charge the same money
        # twice, and nothing would say which figure the buyer was given.
        sa.UniqueConstraint("settlement_id", name="UQ_tcs_collections_settlement"),
        sa.CheckConstraint("tcs_amount >= 0", name="CK_tcs_collections_amount"),
        sa.CheckConstraint("taxable_amount >= 0", name="CK_tcs_collections_taxable"),
        *constraints,
    )
    op.create_index("IX_tcs_collections_firm_id", _COLLECTIONS, ["firm_id"])
    op.create_index(
        "IX_tcs_collections_firm_customer", _COLLECTIONS, ["firm_id", "customer_id"]
    )
    op.create_index(
        "IX_tcs_collections_firm_year",
        _COLLECTIONS,
        ["firm_id", "financial_year_start"],
    )


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the two codes and grant them where the seed says."""
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
    """Give every firm somewhere to book the tax it collects.

    Follows `20260903_0115`, which had to do the same for commission: a
    purpose with no mapping is an error naming the purpose, never a fallback,
    so an unmapped firm would simply be unable to take a receipt once the
    section was switched on.
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
                        ":kind, true, false, false, false, "
                        "true, false, 1, now(), now())"
                    ),
                    {
                        "id": account_id,
                        "firm": firm_id,
                        "group": group_id,
                        "code": code,
                        "name": name,
                        "kind": account_type,
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
    """Create the TCS tables, their permissions, and the account they post to."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _seed_permissions(inspector)
    _seed_control_accounts(inspector)


def downgrade() -> None:
    """Drop the tables and the mapping, leaving the permission codes in place.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than two extra catalogue rows.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_COLLECTIONS):
        op.drop_table(_COLLECTIONS)
    if inspector.has_table(_SETTINGS):
        op.drop_table(_SETTINGS)
    if inspector.has_table("firm_control_accounts"):
        op.execute(
            sa.text("DELETE FROM firm_control_accounts WHERE purpose = 'TCS_PAYABLE'")
        )
